#pragma once
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"
struct cJSON;
esp_err_t amoled_wifi_start(void);
void amoled_wifi_cancel(void);
bool amoled_wifi_configured(void);
bool amoled_wifi_connected(void);
/* Formats the STA IPv4 address into buf; returns false when not connected. */
bool amoled_wifi_ip(char *,size_t);
unsigned amoled_wifi_ota_stage(void);
bool amoled_wifi_transferring(void);
/* Only call from the local USB parser, never a BLE/network RPC. */
bool amoled_wifi_console(struct cJSON *request);
bool amoled_wifi_ota_request(void);
/* Same gates as an explicit OTA request. Skips download when the cloud image is not newer. */
bool amoled_wifi_ota_check(void);

bool amoled_wifi_endpoint(char *,size_t);

esp_err_t amoled_wifi_runtime_error(void);

unsigned amoled_wifi_received(void);
unsigned amoled_wifi_total(void);
bool amoled_wifi_auto_update(void);
