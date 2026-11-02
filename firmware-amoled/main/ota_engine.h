#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdatomic.h>
typedef struct {
 bool (*begin)(void *,uint32_t);
 bool (*write)(void *,const uint8_t *,size_t);
 bool (*verify)(void *,const uint8_t[32]);
 bool (*commit)(void *);
 void (*abort)(void *);
 void (*restart)(void *);
} pc_ota_hooks;
typedef struct {
 pc_ota_hooks hooks;void *ctx;
 atomic_uint epoch,state,error,progress;
 atomic_ullong grant_until;
 atomic_bool reserved;
 unsigned worker_epoch;uint32_t total,written;uint64_t last;
 uint8_t digest[32];bool open;
} pc_ota;
void pc_ota_init(pc_ota *,pc_ota_hooks,void *);
unsigned pc_ota_epoch(pc_ota *);
unsigned pc_ota_state(pc_ota *);
bool pc_ota_busy(pc_ota *);
bool pc_ota_cancel(pc_ota *);
void pc_ota_grant(pc_ota *,uint64_t);
void pc_ota_tick(pc_ota *,uint64_t);
void pc_ota_process(pc_ota *,unsigned,const uint8_t *,size_t,uint64_t);
