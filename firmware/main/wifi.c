#include "wifi.h"

#include <string.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "nvs.h"
#include "nvs_flash.h"

#include "config.h"

static const char *TAG = "wifi";

static EventGroupHandle_t events;
#define EV_CONNECTED BIT0

static bool got_ip;

static void on_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg; (void)base;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        got_ip = false;
        xEventGroupClearBits(events, EV_CONNECTED);
        ESP_LOGI(TAG, "disconnected, retrying");
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        got_ip = true;
        xEventGroupSetBits(events, EV_CONNECTED);
        ESP_LOGI(TAG, "got ip");
    }
}

void wifi_init(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_event, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_event, NULL, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    events = xEventGroupCreate();

    char ssid[33] = {0}, pass[65] = {0};
    size_t ssid_len = sizeof(ssid), pass_len = sizeof(pass);
    bool saved = false;
    nvs_handle_t n;
    if (nvs_open("wifi", NVS_READONLY, &n) == ESP_OK) {
        saved = nvs_get_str(n, "ssid", ssid, &ssid_len) == ESP_OK &&
                nvs_get_str(n, "pass", pass, &pass_len) == ESP_OK;
        nvs_close(n);
    }
    if (!saved && sizeof(WIFI_DEFAULT_SSID) > 1) {
        strlcpy(ssid, WIFI_DEFAULT_SSID, sizeof(ssid));
        strlcpy(pass, WIFI_DEFAULT_PASS, sizeof(pass));
        saved = true;
    }
    if (saved) {
        wifi_config_t wc = {0};
        strlcpy((char *)wc.sta.ssid, ssid, sizeof(wc.sta.ssid));
        strlcpy((char *)wc.sta.password, pass, sizeof(wc.sta.password));
        wc.sta.threshold.authmode = WIFI_AUTH_WPA_PSK;
        ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wc));
        ESP_ERROR_CHECK(esp_wifi_start());
        ESP_LOGI(TAG, "sta started for saved ssid");
    } else {
        ESP_LOGI(TAG, "no wifi credentials; USB-only mode");
    }
}

bool wifi_sta_save_and_connect(const char *ssid, const char *pass)
{
    if (!ssid || !*ssid || (pass && strlen(pass) > 0 && strlen(pass) < 8)) return false;
    nvs_handle_t n;
    if (nvs_open("wifi", NVS_READWRITE, &n) != ESP_OK) return false;
    nvs_set_str(n, "ssid", ssid);
    nvs_set_str(n, "pass", pass ? pass : "");
    nvs_commit(n);
    nvs_close(n);

    wifi_config_t wc = {0};
    strlcpy((char *)wc.sta.ssid, ssid, sizeof(wc.sta.ssid));
    if (pass) strlcpy((char *)wc.sta.password, pass, sizeof(wc.sta.password));
    wc.sta.threshold.authmode = WIFI_AUTH_WPA_PSK;
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wc));
    static bool started;
    if (!started) { ESP_ERROR_CHECK(esp_wifi_start()); started = true; }
    else esp_wifi_connect();
    return true;
}

bool wifi_sta_wait(unsigned timeout_ms)
{
    if (!events) return false;
    return (xEventGroupWaitBits(events, EV_CONNECTED, pdFALSE, pdFALSE,
                                pdMS_TO_TICKS(timeout_ms)) & EV_CONNECTED) != 0;
}

bool wifi_sta_connected(void) { return got_ip; }

void hand_wifi_stop(void)
{
    if (events) { xEventGroupClearBits(events, EV_CONNECTED); got_ip = false; }
    esp_wifi_disconnect();
}
