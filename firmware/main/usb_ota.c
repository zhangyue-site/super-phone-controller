#include "usb_ota.h"

#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <sys/select.h>
#include <unistd.h>

#include "esp_app_desc.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mbedtls/sha256.h"

#include "ota_guard.h"

static const char *TAG = "usb_ota";
#define IDLE_TIMEOUT_MS 30000
#define CHUNK 4096

/* Runs on its own task so the console line reader stays responsive for
 * "OTA-CANCEL". During the transfer USB-Serial-JTAG may briefly reconnect
 * when flash is written; ota_guard keeps other writers out and the host is
 * expected to re-open the port and resume (TODO: offset-resume protocol). */
struct ctx {
    unsigned size;
    char expected[65];
};

static int read_blocking(uint8_t *buf, size_t want, int timeout_ms)
{
    fd_set set;
    struct timeval tv = { .tv_sec = timeout_ms / 1000, .tv_usec = (timeout_ms % 1000) * 1000 };
    FD_ZERO(&set);
    FD_SET(0, &set);
    if (select(1, &set, NULL, NULL, &tv) <= 0) return -ETIMEDOUT;
    return (int)read(0, buf, want);
}

static void worker(void *arg)
{
    struct ctx *c = (struct ctx *)arg;
    const esp_partition_t *partition = esp_ota_get_next_update_partition(NULL);
    esp_ota_handle_t handle = 0;
    bool writing = false;

    if (!partition || c->size < 1024 || c->size > partition->size) {
        printf("OTA-FAIL size\n");
        goto out;
    }
    /* Make stdin blocking for the raw stream, restore afterwards. */
    int flags = fcntl(0, F_GETFL, 0);
    fcntl(0, F_SETFL, flags & ~O_NONBLOCK);

    if (esp_ota_begin(partition, c->size, &handle) != ESP_OK) {
        printf("OTA-FAIL begin\n");
        goto restore;
    }
    writing = true;

    {
        mbedtls_sha256_context sha;
        mbedtls_sha256_init(&sha);
        mbedtls_sha256_starts(&sha, 0);

        static uint8_t buf[CHUNK];
        unsigned received = 0;
        while (received < c->size) {
            size_t want = (c->size - received) < CHUNK ? (c->size - received) : CHUNK;
            int n = read_blocking(buf, want, IDLE_TIMEOUT_MS);
            if (n <= 0) {
                printf("OTA-FAIL timeout\n");
                mbedtls_sha256_free(&sha);
                goto restore;
            }
            mbedtls_sha256_update(&sha, buf, (size_t)n);
            if (esp_ota_write(handle, buf, (size_t)n) != ESP_OK) {
                printf("OTA-FAIL flash\n");
                mbedtls_sha256_free(&sha);
                goto restore;
            }
            received += (unsigned)n;
        }

        unsigned char digest[32];
        char actual[65] = {};
        mbedtls_sha256_finish(&sha, digest);
        mbedtls_sha256_free(&sha);
        for (int i = 0; i < 32; ++i) snprintf(actual + i * 2, 3, "%02x", digest[i]);
        if (strcmp(actual, c->expected)) {
            printf("OTA-FAIL sha256\n");
            goto restore;
        }
    }

    if (esp_ota_end(handle) != ESP_OK) { writing = false; printf("OTA-FAIL end\n"); goto restore; }
    writing = false;
    if (!ota_guard_commit(OTA_POWER)) { printf("OTA-FAIL guard\n"); goto restore; }
    if (esp_ota_set_boot_partition(partition) != ESP_OK) { printf("OTA-FAIL boot\n"); goto restore; }
    printf("OTA-OK %s\n", esp_app_get_description()->version);
    ESP_LOGI(TAG, "usb ota complete, slot=%s, rebooting", partition->label);
    fcntl(0, F_SETFL, flags);
    vTaskDelay(pdMS_TO_TICKS(1000));
    esp_restart();

restore:
    fcntl(0, F_SETFL, flags);
    if (writing) esp_ota_abort(handle);
out:
    ota_guard_release(OTA_POWER);
    free(c);
    vTaskDelete(NULL);
}

bool usb_ota_handle_line(const char *line)
{
    if (strncmp(line, "OTA\t", 4)) return false;
    struct ctx *c = (struct ctx *)calloc(1, sizeof(*c));
    if (!c) return true;
    if (sscanf(line + 4, "%u\t%64s", &c->size, c->expected) != 2 || strlen(c->expected) != 64) {
        printf("OTA-FAIL args\n");
        free(c);
        return true;
    }
    if (!ota_guard_acquire(OTA_POWER)) {
        printf("OTA-FAIL busy\n");
        free(c);
        return true;
    }
    printf("OTA-READY\n");
    if (xTaskCreate(worker, "usb_ota", 8192, c, 3, NULL) != pdPASS) {
        printf("OTA-FAIL task\n");
        ota_guard_release(OTA_POWER);
        free(c);
    }
    return true;
}

void usb_ota_init(void)
{
    /* Currently the line router in link.c calls usb_ota_handle_line(); nothing
     * else to set up yet (TODO: offset-resume, host-side flasher tool). */
}
