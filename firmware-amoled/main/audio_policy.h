#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
typedef struct {unsigned epoch;uint64_t started,energy;size_t bytes;bool active,cancelled;} pc_audio_take;
void pc_audio_take_init(pc_audio_take *);
bool pc_audio_take_begin(pc_audio_take *,unsigned,uint64_t);
bool pc_audio_take_append(pc_audio_take *,unsigned,uint64_t,size_t,unsigned rms);
bool pc_audio_take_finish(const pc_audio_take *);
