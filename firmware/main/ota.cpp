#include "ota.h"
#include "ota_guard.h"
#include "wifi.h"

#include <atomic>
#include <cstdio>
#include <cstring>
#include <string>

#include "esp_app_desc.h"
#include "esp_crt_bundle.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_partition.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs.h"
#include "psa/crypto.h"

#include "config.h"

static const char *TAG = "ota";
#define PROJECT_NAME "phone-hand"
#define DL_ATTEMPTS 5
#define READ_TIMEOUT_MS 15000

static std::atomic<bool> busy(false);
static std::atomic<int> stage(0), progress(0);
static void set_stage(int v) { stage = v; }

static esp_http_client_handle_t open_url(const char *path, bool ranged, unsigned offset)
{
    char url[320];
    snprintf(url, sizeof(url), "%s%s", OTA_URL, path);
    esp_http_client_config_t cfg = {};
    cfg.url = url;
    cfg.timeout_ms = READ_TIMEOUT_MS;
    cfg.crt_bundle_attach = esp_crt_bundle_attach;
    cfg.buffer_size = 4096;
    auto c = esp_http_client_init(&cfg);
    if (!c) return nullptr;
    if (sizeof(OTA_TOKEN) > 1) esp_http_client_set_header(c, "Authorization", "Bearer " OTA_TOKEN);
    if (ranged) {
        char range[48];
        snprintf(range, sizeof(range), "bytes=%u-", offset);
        esp_http_client_set_header(c, "Range", range);
    }
    if (esp_http_client_open(c, 0) != ESP_OK) { esp_http_client_cleanup(c); return nullptr; }
    if (esp_http_client_fetch_headers(c) < 0) { esp_http_client_close(c); esp_http_client_cleanup(c); return nullptr; }
    return c;
}

static void close_url(esp_http_client_handle_t c)
{
    if (c) { esp_http_client_close(c); esp_http_client_cleanup(c); }
}

static bool report(const char *phase)
{
    char url[320], body[256];
    snprintf(url, sizeof(url), "%s/report", OTA_URL);
    const auto *p = esp_ota_get_running_partition();
    esp_ota_img_states_t state = ESP_OTA_IMG_UNDEFINED;
    esp_ota_get_state_partition(p, &state);
    snprintf(body, sizeof(body),
             "{\"version\":\"%s\",\"slot\":\"%s\",\"phase\":\"%s\",\"imageState\":%d}",
             esp_app_get_description()->version, p->label, phase, (int)state);
    esp_http_client_config_t cfg = {};
    cfg.url = url;
    cfg.timeout_ms = READ_TIMEOUT_MS;
    cfg.crt_bundle_attach = esp_crt_bundle_attach;
    auto c = esp_http_client_init(&cfg);
    if (!c) return false;
    if (sizeof(OTA_TOKEN) > 1) esp_http_client_set_header(c, "Authorization", "Bearer " OTA_TOKEN);
    esp_http_client_set_header(c, "Content-Type", "application/json");
    esp_http_client_set_method(c, HTTP_METHOD_POST);
    esp_http_client_set_post_field(c, body, strlen(body));
    esp_err_t err = esp_http_client_perform(c);
    int status = esp_http_client_get_status_code(c);
    esp_http_client_cleanup(c);
    ESP_LOGI(TAG, "report phase=%s status=%d", phase, status);
    return err == ESP_OK && status == 200;
}

/* One HTTPS OTA attempt. The hash context spans the whole image, so an
 * interrupted download resumes with HTTP Range while keeping the context. */
static bool attempt(void)
{
    esp_ota_handle_t handle = 0;
    bool writing = false;
    esp_http_client_handle_t c = nullptr;
    unsigned size = 0, received = 0, reconnects = 0;
    char expected[65] = {}, version[32] = {};
    bool ok = false;

    do {
        /* 1. manifest: "PCOTA1\n<size>\n<sha256hex>\n<version>" */
        c = open_url("/manifest", false, 0);
        if (!c || esp_http_client_get_status_code(c) != 200) break;
        char manifest[256] = {};
        int length = (int)esp_http_client_get_content_length(c);
        if (length < 1 || length >= (int)sizeof(manifest)) break;
        int got = esp_http_client_read_response(c, manifest, length);
        close_url(c); c = nullptr;
        if (got != length ||
            sscanf(manifest, "PCOTA1\n%u\n%64[0-9a-f]\n%31s", &size, expected, version) != 3 ||
            strlen(expected) != 64) break;

        const auto *partition = esp_ota_get_next_update_partition(nullptr);
        if (!partition || size < 1024 || size > partition->size) break;
        if (!strcmp(version, esp_app_get_description()->version)) {
            set_stage(4); ok = true;
            ESP_LOGI(TAG, "already on version %s", version);
            break;
        }

        /* 2. begin + stream + hash */
        if (esp_ota_begin(partition, size, &handle) != ESP_OK) break;
        writing = true;

        psa_hash_operation_t hash = psa_hash_operation_init();
        if (psa_hash_setup(&hash, PSA_ALG_SHA_256) != PSA_SUCCESS) break;

        bool streamed = false;
        while (!streamed && reconnects < DL_ATTEMPTS && !ota_guard_cancelled(OTA_WIFI)) {
            if (reconnects > 0) {
                ESP_LOGW(TAG, "resume from %u (reconnect %u)", received, reconnects);
                close_url(c); c = nullptr;
                char path[48];
                snprintf(path, sizeof(path), "/%s.bin", version);
                c = open_url(path, true, received);
                if (!c) break;
                int status = esp_http_client_get_status_code(c);
                long long clen = (long long)esp_http_client_get_content_length(c);
                if (status != 206 || clen != (long long)(size - received)) {
                    ESP_LOGW(TAG, "resume rejected (status=%d len=%lld)", status, clen);
                    break;
                }
            } else {
                char path[48];
                snprintf(path, sizeof(path), "/%s.bin", version);
                c = open_url(path, false, 0);
                if (!c) break;
                if (esp_http_client_get_status_code(c) != 200) break;
            }

            static uint8_t buffer[4096];
            int n;
            while (received < size && (n = esp_http_client_read(c, (char *)buffer,
                                            (size - received) < sizeof(buffer) ? (size - received) : sizeof(buffer))) > 0) {
                if (ota_guard_cancelled(OTA_WIFI)) break;
                if (psa_hash_update(&hash, buffer, n) != PSA_SUCCESS) break;
                if (esp_ota_write(handle, buffer, n) != ESP_OK) break;
                received += (unsigned)n;
                progress = received * 100 / size;
            }
            close_url(c); c = nullptr;
            streamed = (received == size);
            if (!streamed && !ota_guard_cancelled(OTA_WIFI)) ++reconnects;
        }

        unsigned char digest[32];
        size_t digest_size = 0;
        char actual[65] = {};
        if (!streamed || ota_guard_cancelled(OTA_WIFI)) break;
        if (psa_hash_finish(&hash, digest, sizeof(digest), &digest_size) != PSA_SUCCESS ||
            digest_size != 32) break;
        for (int i = 0; i < 32; ++i) snprintf(actual + i * 2, 3, "%02x", digest[i]);
        if (strcmp(actual, expected)) { ESP_LOGW(TAG, "sha256 mismatch"); break; }

        /* 3. commit */
        auto end_err = esp_ota_end(handle);
        writing = false;
        if (end_err != ESP_OK) { ESP_LOGE(TAG, "esp_ota_end: %s", esp_err_to_name(end_err)); break; }
        esp_app_desc_t desc = {};
        if (esp_ota_get_partition_description(partition, &desc) != ESP_OK ||
            strcmp(desc.version, version) || strcmp(desc.project_name, PROJECT_NAME)) {
            ESP_LOGW(TAG, "candidate desc mismatch (version=%s project=%s)", desc.version, desc.project_name);
            break;
        }
        if (!ota_guard_commit(OTA_WIFI)) break;
        if (esp_ota_set_boot_partition(partition) != ESP_OK) break;
        set_stage(3); ok = true;
        ESP_LOGI(TAG, "verified version=%s bytes=%u slot=%s", version, size, partition->label);
    } while (false);

    close_url(c);
    if (writing) esp_ota_abort(handle);
    return ok;
}

static void worker(void *)
{
    bool ok = false;
    for (int i = 0; i < DL_ATTEMPTS && !ok && !ota_guard_cancelled(OTA_WIFI); ++i) {
        if (i > 0) { ESP_LOGW(TAG, "retry attempt %d", i + 1); vTaskDelay(pdMS_TO_TICKS(2000)); }
        ok = attempt();
    }
    if (!ok) set_stage(5);
    if (ok && stage == 3) {
        report("installed");
        vTaskDelay(pdMS_TO_TICKS(1500));
        esp_restart();
    }
    busy = false;
    ota_guard_release(OTA_WIFI);
    report(ok ? "current" : "failed");
    vTaskDelete(nullptr);
}

bool phone_hand_ota_start(void)
{
    if (!ota_guard_acquire(OTA_WIFI)) return false;
    busy = true; progress = 0; set_stage(1);
    if (xTaskCreate(worker, "ota", 12288, nullptr, 3, nullptr) != pdPASS) {
        set_stage(5); busy = false; ota_guard_release(OTA_WIFI);
        return false;
    }
    return true;
}

bool phone_hand_ota_busy(void) { return busy; }
int phone_hand_ota_stage(void) { return stage; }
int phone_hand_ota_progress(void) { return progress; }

static void confirm_task(void *)
{
    const esp_partition_t *p = esp_ota_get_running_partition();
    esp_ota_img_states_t state;
    if (esp_ota_get_state_partition(p, &state) == ESP_OK && state == ESP_OTA_IMG_PENDING_VERIFY) {
        /* 90 s of healthy uptime confirms the slot; the bootloader rolls back
         * on its own if we never make it here. */
        vTaskDelay(pdMS_TO_TICKS(90000));
        auto err = esp_ota_mark_app_valid_cancel_rollback();
        ESP_LOGI(TAG, "boot confirmed slot=%s result=%s", p->label, esp_err_to_name(err));
        report("boot-confirmed");
    }
    vTaskDelete(nullptr);
}

void phone_hand_ota_confirm_start(void)
{
    xTaskCreate(confirm_task, "ota_confirm", 6144, nullptr, 2, nullptr);
}
