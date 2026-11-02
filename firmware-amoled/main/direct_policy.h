#pragma once
#include <stdbool.h>
#include <stdint.h>
/* Worker-owned policy. Caller serializes with USB owner/OTA reservation.
 * This module does not arm HID, parse HTTP or authorize screen capture. */
typedef struct {
 unsigned epoch,count;
 bool running;
 uint64_t until;
 char lease[65],task[33],retired[64][33];
} pc_direct;
void pc_direct_init(pc_direct *);
void pc_direct_cancel(pc_direct *);
bool pc_direct_lease(pc_direct *,const char *);
bool pc_direct_claim_ready(const pc_direct *,bool usb,bool local_consent,bool ble,bool ota);
bool pc_direct_begin(pc_direct *,const char *,uint64_t now,bool usb,bool local_consent,bool ble,bool ota);
/* Retire the action ID BEFORE USB submission. Failed/partial/unknown execution
 * and lost ACKs do not make IDs reusable during the turn. */
bool pc_direct_reserve(pc_direct *,const char *,uint64_t now,bool usb,bool local_consent,bool ble,bool ota);
