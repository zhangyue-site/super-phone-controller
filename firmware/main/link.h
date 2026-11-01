#pragma once

/* USB serial control + OTA command router. WiFi is optional (STA, provisioned
 * from the host or config.h); HTTPS OTA needs it. USB serial passthrough OTA
 * (OTA\t<size>\t<sha256>) is the no-WiFi fallback.
 *
 * Commands (one per line, tab-separated):
 *   SKILL / SKILL2 / WAIT / LISTEN / FAIL / END   LED states (unchanged)
 *   WIFI\t<ssid>\t<pass>                          save + connect STA
 *   WIFIOFF                                       disconnect
 *   OTA                                           start HTTPS OTA
 *   OTA\t<size>\t<sha256hex>                      USB passthrough OTA
 *   OTA-CANCEL                                    cancel WiFi OTA
 *   OTA-STATUS                                    print stage/progress
 *   OTA-CONFIRM                                   confirm current slot
 *
 * A WIFI line is ignored in USB-only builds (feature parity with the
 * original firmware) only when WiFi was compiled out.
 */

void link_start(void);
