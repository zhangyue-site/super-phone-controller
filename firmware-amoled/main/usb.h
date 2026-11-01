#pragma once
#include <stdbool.h>
#include "esp_err.h"
#include <stddef.h>
esp_err_t amoled_usb_start(void);
bool amoled_usb_ready(void);
void amoled_usb_gate(bool enable);
bool amoled_usb_armed(void);
bool amoled_usb_consumer(unsigned usage);
bool amoled_usb_mouse(int dx,int dy,bool click);
size_t amoled_usb_read(char *out,size_t size);
void amoled_usb_write(const char *text);
const char *amoled_usb_serial(void);
size_t amoled_usb_write_bytes(const void *data,size_t size);
esp_err_t amoled_usb_enter_bootloader(void);
