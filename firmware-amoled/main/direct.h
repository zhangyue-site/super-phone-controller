#pragma once
#include <stdbool.h>
#include "esp_err.h"
esp_err_t amoled_direct_start(void);
void amoled_direct_cancel(void);
bool amoled_direct_online(void);

/* Board-local long-press only; never call from HTTP/BLE commands. */
bool amoled_direct_enable(void);
