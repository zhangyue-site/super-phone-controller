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

bool controller_preflight_probe();

void controller_voice_prepare();
bool controller_voice_prepared();

#include <atomic>
struct VoiceStream {
 const unsigned char *pcm=nullptr;
 std::atomic<unsigned> bytes{0};
 std::atomic<bool> done{false},abort{false};
 std::atomic<int> result{0};
 std::atomic<int64_t> finished_at{0};
 unsigned sequence=0;
};
bool controller_voice_stream_upload(VoiceStream &stream);
