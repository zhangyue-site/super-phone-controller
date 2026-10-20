#pragma once
#include <stdint.h>
void controller_adb_init();
bool controller_adb_activate(uint32_t consent);
void controller_adb_cancel();
int controller_adb_stage();
uint32_t controller_adb_ticket();

int controller_adb_error();
