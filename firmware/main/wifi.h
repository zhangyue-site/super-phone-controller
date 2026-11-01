#pragma once
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Bring up esp_netif/event loop and (if credentials exist) start STA.
 * Safe to call once at boot; never blocks. */
void wifi_init(void);

/* Save credentials to NVS and (re)connect. Returns false on invalid args. */
bool wifi_sta_save_and_connect(const char *ssid, const char *pass);

/* Block until station got an IP or timeout_ms elapsed. */
bool wifi_sta_wait(unsigned timeout_ms);

bool wifi_sta_connected(void);
void hand_wifi_stop(void);

#ifdef __cplusplus
}
#endif
