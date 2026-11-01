#pragma once
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* HTTPS OTA over WiFi (ported from firmware-epaper, slimmed down):
 * manifest -> SHA256-verified download with resume -> set boot slot -> report.
 * All flash work runs on a worker task behind ota_guard. */
bool phone_hand_ota_start(void);   /* false if already busy */
bool phone_hand_ota_busy(void);
int  phone_hand_ota_stage(void);   /* 0 idle 1 fetching 2 downloading 3 done 4 same-version 5 failed */
int  phone_hand_ota_progress(void);/* 0..100 */

/* Mark the running slot valid (cancels rollback) and report boot. */
void phone_hand_ota_confirm_start(void);

#ifdef __cplusplus
}
#endif
