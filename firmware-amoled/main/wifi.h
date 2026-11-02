#pragma once
#include <stdbool.h>
#include "esp_err.h"
struct cJSON;
esp_err_t amoled_wifi_start(void);
void amoled_wifi_cancel(void);
bool amoled_wifi_configured(void);
bool amoled_wifi_connected(void);
unsigned amoled_wifi_ota_stage(void);
/* Only call from the local USB parser, never a BLE/network RPC. */
bool amoled_wifi_console(struct cJSON *request);
