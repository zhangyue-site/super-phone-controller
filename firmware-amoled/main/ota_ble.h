#pragma once
#include "esp_err.h"
#include <stdbool.h>
#include <stdint.h>
struct ble_gatt_access_ctxt;
esp_err_t amoled_ota_init(void);
void amoled_ota_connect(uint16_t);
void amoled_ota_disconnect(void);
void amoled_ota_cancel(void);
bool amoled_ota_busy(void);
bool amoled_ota_ready(void);
void amoled_ota_status(uint8_t out[4]);
int amoled_ota_access(uint16_t,uint16_t,struct ble_gatt_access_ctxt *,void *);
extern uint16_t amoled_ota_status_handle;
