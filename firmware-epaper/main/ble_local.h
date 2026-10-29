#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
int controller_ble_local_start(void);
void controller_ble_local_connect(uint16_t conn);
void controller_ble_local_disconnect(uint16_t conn);
void controller_ble_local_cancel(void);
bool controller_ble_local_owns_input(void);
bool controller_ble_local_connected(void);
bool controller_ble_relay_online(void);
int controller_ble_local_write(uint16_t conn,const uint8_t *packet,size_t size);
int controller_ble_local_read(uint16_t conn,char *out,size_t size);
#ifdef __cplusplus
}
#endif
