#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
typedef struct {unsigned stage;size_t received,total;char heard[481],reply[481],detail[160];} companion_speech_state;
void companion_speech_reset(void);
void companion_speech_stop(void);
void companion_speech_snapshot(companion_speech_state *out);
bool companion_speech_run(const uint8_t *pcm,size_t size,unsigned epoch,const char *session,bool (*live)(uint32_t));

void companion_speech_init(void);
unsigned companion_speech_volume(void);
void companion_speech_set_volume(unsigned volume);
bool companion_speech_test(unsigned epoch,bool (*live)(uint32_t));
