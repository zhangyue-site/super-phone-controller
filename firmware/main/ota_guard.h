#pragma once
#include <stdbool.h>
#ifdef __cplusplus
extern "C" {
#endif
enum { OTA_WIFI=1, OTA_BLE=2, OTA_POWER=3 };
enum ota_guard_phase { OTA_GUARD_IDLE, OTA_GUARD_WRITING, OTA_GUARD_COMMIT, OTA_GUARD_POWER };
enum ota_guard_phase ota_guard_get_phase(void);
bool ota_guard_acquire(unsigned owner);
void ota_guard_cancel(unsigned owner);
bool ota_guard_cancelled(unsigned owner);
bool ota_guard_commit(unsigned owner);
void ota_guard_release(unsigned owner);
#ifdef __cplusplus
}
#endif
