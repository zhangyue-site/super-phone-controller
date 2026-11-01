#pragma once
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* USB serial passthrough upgrade channel (fallback when WiFi is down).
 * Protocol over the USB-Serial-JTAG console, from the host:
 *   "OTA\t<size>\t<sha256-hex>\n"   -> device replies "OTA-READY\n"
 *   <size> raw firmware bytes       -> device hashes + writes to ota slot
 *   device replies "OTA-OK <ver>\n" or "OTA-FAIL <reason>\n"
 * A 30 s idle gap aborts the transfer. Uses ota_guard so it cannot run
 * concurrently with the WiFi OTA. */
void usb_ota_init(void);
bool usb_ota_handle_line(const char *line);

#ifdef __cplusplus
}
#endif
