#pragma once
#include "esp_err.h"
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
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

/* Local-maintenance Wi-Fi transport feeds the same single flash writer. */
bool amoled_ota_wifi_begin(const char *,uint32_t,const uint8_t[32],uint64_t,unsigned *);
bool amoled_ota_wifi_chunk(unsigned,const uint8_t *,size_t,bool);
bool amoled_ota_wifi_live(unsigned);

/* Block new transfers, cancel before commit and await actual worker abort. */
bool amoled_ota_prepare_power(void);
bool amoled_ota_power_idle(void);
void amoled_ota_finish_power(void);
