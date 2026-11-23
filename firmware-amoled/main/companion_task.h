#pragma once
#include "companion_progress.h"
#include "cJSON.h"
/* Observers only: never grant permission, issue input or create tasks. */
void amoled_companion_begin(unsigned source,unsigned epoch,const char *task);
void amoled_companion_event(unsigned source,unsigned epoch,pc_phase phase,unsigned round,unsigned completed,const char *detail,bool verified);
void amoled_companion_remote(unsigned source,unsigned epoch,const cJSON *reply);
void amoled_companion_stop(void);
void amoled_companion_fence(unsigned source,unsigned minimum_epoch);
void amoled_companion_stop_ack(unsigned source);
void amoled_companion_snapshot(pc_companion *out);

unsigned amoled_companion_stop_generation(void);
void amoled_companion_monitor_result(unsigned epoch,unsigned requested_stop,const cJSON *reply);
