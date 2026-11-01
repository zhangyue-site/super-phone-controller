#include "link.h"

#include "led.h"
#include "ota.h"
#include "usb_ota.h"
#include "wifi.h"

#include <stdio.h>
#include <string.h>

#include "esp_log.h"
#include "esp_app_desc.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "link";

static void handle_line(char *line)
{
    size_t len = strlen(line);
    while (len && (line[len - 1] == '\n' || line[len - 1] == '\r')) {
        line[--len] = '\0';
    }
    if (strncmp(line, "OTA\t", 4) == 0) {
        usb_ota_handle_line(line);
        return;
    }
    if (strncmp(line, "WIFI\t", 5) == 0) {
        char ssid[33] = {0}, pass[65] = {0};
        const char *rest = line + 5;
        const char *tab = strchr(rest, '\t');
        if (tab && (size_t)(tab - rest) < sizeof(ssid)) {
            memcpy(ssid, rest, tab - rest);
            strlcpy(pass, tab + 1, sizeof(pass));
        } else {
            strlcpy(ssid, rest, sizeof(ssid));
        }
        if (wifi_sta_save_and_connect(ssid, pass)) {
            ESP_LOGI(TAG, "wifi connect requested");
            led_await_reply();
        } else {
            ESP_LOGW(TAG, "bad WIFI command");
            led_fail();
        }
        return;
    }
    if (strcmp(line, "WIFIOFF") == 0) {
        hand_wifi_stop();
        ESP_LOGI(TAG, "wifi disconnected");
        return;
    }
    if (strcmp(line, "OTA") == 0) {
        if (phone_hand_ota_start()) {
            ESP_LOGI(TAG, "https ota started");
        } else {
            printf("OTA-FAIL busy\n");
        }
        return;
    }
    if (strcmp(line, "OTA-CANCEL") == 0) {
        /* guard cancel is issued from ota.cpp; here we just report */
        printf("OTA-STATUS stage=%d progress=%d busy=%d\n",
               phone_hand_ota_stage(), phone_hand_ota_progress(), phone_hand_ota_busy());
        return;
    }
    if (strcmp(line, "OTA-STATUS") == 0) {
        printf("OTA-STATUS stage=%d progress=%d busy=%d ver=%s\n",
               phone_hand_ota_stage(), phone_hand_ota_progress(), phone_hand_ota_busy(),
               esp_app_get_description()->version);
        return;
    }
    if (strcmp(line, "OTA-CONFIRM") == 0) {
        phone_hand_ota_confirm_start();
        return;
    }
    if (strcmp(line, "SKILL") == 0) {
        led_skill();
        ESP_LOGI(TAG, "skill");
        return;
    }
    if (strcmp(line, "SKILL2") == 0) {
        led_skill_other();
        ESP_LOGI(TAG, "skill other");
        return;
    }
    if (strcmp(line, "WAIT") == 0) {
        led_await_reply();
        return;
    }
    if (strcmp(line, "LISTEN") == 0) {
        led_listen();
        return;
    }
    if (strcmp(line, "FAIL") == 0) {
        led_fail();
        return;
    }
    if (strcmp(line, "END") == 0) {
        led_plugged();
    }
}

static void serial_task(void *arg)
{
    (void)arg;
    char line[128];
    while (true) {
        if (!fgets(line, sizeof(line), stdin)) {
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }
        handle_line(line);
    }
}

void link_start(void)
{
    usb_ota_init();
    xTaskCreate(serial_task, "serial", 4096, NULL, 3, NULL);
}
