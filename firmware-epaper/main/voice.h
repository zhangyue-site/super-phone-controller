#pragma once
void controller_voice_init();
void controller_voice_hold(bool held);
void controller_voice_cancel();
int controller_voice_stage();
void controller_voice_changed(bool completed);
bool controller_voice_online();
bool controller_voice_upload(const unsigned char *pcm,unsigned size,unsigned sequence);

void controller_voice_test();
const char *controller_voice_session();
unsigned controller_voice_cancel_sequence();
