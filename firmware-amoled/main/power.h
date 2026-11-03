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
#ifdef __cplusplus
}
#endif
