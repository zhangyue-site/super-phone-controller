#pragma once
#include <stdbool.h>
#include <stddef.h>
void usb_start(void);
bool usb_ready(void);
void usb_gate(bool enable);
bool usb_armed(void);
bool usb_consumer(unsigned usage);
bool usb_mouse(int dx,int dy,bool click);
size_t usb_read(char *out,size_t size);
void usb_write(const char *text);
