#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
void controller_usb_start(void);
void controller_usb_service(void);
void controller_usb_request_mode(bool enabled);
bool controller_usb_hid_enabled(void);
size_t controller_usb_read(uint8_t *data, size_t size);
void controller_usb_write(const char *text);
void controller_usb_prepare_reset(bool download);
void controller_release(void);
bool controller_usb_ready(void);

bool controller_usb_mouse(int dx,int dy,bool click);
bool controller_usb_phone_key(bool home);

// One-shot AI Home request; true means a USB press/release report was submitted, not observed UI success.
bool controller_usb_ai_home(bool (*live)(unsigned),unsigned sequence);

#include "hid_pointer_policy.h"
bool controller_usb_ai_pointer(const controller::PointerCommand& command,bool (*live)(unsigned),unsigned sequence);

#if CONTROLLER_USB_MAINTENANCE
bool controller_usb_maintenance_pointer(const controller::PointerCommand& command);
#endif

#if CONTROLLER_USB_MAINTENANCE
const char* controller_usb_maintenance_status();
#endif

bool controller_usb_ai_key(bool home,bool (*live)(unsigned),unsigned sequence);
bool controller_usb_key(uint8_t code,bool (*live)(unsigned),unsigned sequence);
bool controller_usb_consumer(uint16_t usage,bool (*live)(unsigned),unsigned sequence);

const char *controller_usb_serial(void);

bool controller_usb_keyboard(uint8_t modifier,uint8_t usage,bool (*live)(unsigned),unsigned sequence);
bool controller_usb_ascii(const uint8_t *text,size_t length,bool (*live)(unsigned),unsigned sequence);
