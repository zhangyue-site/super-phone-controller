#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#ifdef __cplusplus
extern "C" {
#endif
bool controller_board_control_start(void);
bool controller_board_control_busy(void);
void controller_board_control_connect(uint16_t conn);
void controller_board_control_disconnect(void);
int controller_board_control_write(uint16_t conn,const uint8_t *packet,size_t length);
int controller_board_control_read(uint16_t conn,uint8_t *out,size_t capacity);
bool controller_board_usb_command(const char *line);
#ifdef __cplusplus
}
#endif
