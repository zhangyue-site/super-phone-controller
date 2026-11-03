#pragma once
#include <stdbool.h>
#include "esp_err.h"
esp_err_t amoled_direct_start(void);
void amoled_direct_cancel(void);
bool amoled_direct_online(void);

/* Board-local long-press only; never call from HTTP/BLE commands. */
bool amoled_direct_enable(void);

/* Local plugin confirmation may restrict the next consumed task identity. */
bool amoled_direct_enable_task(const char *);

unsigned amoled_direct_epoch(void);
bool amoled_direct_enable_task_epoch(const char *,unsigned expected_epoch);
