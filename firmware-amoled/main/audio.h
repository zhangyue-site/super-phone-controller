#pragma once
#include <stdbool.h>
#include <stddef.h>
/* Explicit board-local PRESS/RELEASE only. No background microphone task. */
bool amoled_audio_press(void);
void amoled_audio_release(void);
void amoled_audio_cancel(void);
bool amoled_audio_busy(void);
unsigned amoled_audio_stage(void);
unsigned amoled_audio_duration_ms(void);

bool amoled_audio_result(char *,size_t);
