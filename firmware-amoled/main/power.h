#pragma once
#include "esp_err.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Call once after BSP display initialization, from task context. On success the
 * PMIC's physical PWR long press requests hardware power-off. Its existing
 * duration is preserved. USB/battery shutdown behavior awaits board validation. */
esp_err_t amoled_power_init(void);
/* Requires successful init. ESP_OK means I2C accepted the shutdown command;
 * it does not prove rails dropped. The caller must handle power remaining on.
 * Call only after stopping OTA writes and other work requiring power. */
esp_err_t amoled_power_shutdown(void);
/* Arm the AXP2101 short-press status bit. Long press stays a hardware power-off. */
esp_err_t amoled_power_arm_key(void);
/* 1 when a new PWR short press is latched. Clears that status bit. */
int amoled_power_take_short_press(void);
/* AXP2101 STATUS1 bit 5, the same bit XPowersLib calls isVbusIn().
 * *known is 1 only after a successful read. A failed read must not be treated
 * as cable-removed, because callers gate real USB input on this. */
int amoled_power_vbus_present(int *known);
#ifdef __cplusplus
}
#endif
