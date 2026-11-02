#pragma once
#include <stdbool.h>
#include "esp_err.h"
esp_err_t amoled_relay_start(void);
bool amoled_relay_connected(void);
bool amoled_relay_online(void);
void amoled_relay_cancel(void);
void amoled_relay_usb_detached(void);

bool amoled_relay_ready(void);
