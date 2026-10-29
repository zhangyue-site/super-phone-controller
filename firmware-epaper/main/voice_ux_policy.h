#pragma once
#include <cstdint>
namespace controller {
constexpr unsigned voice_min_samples=6400;
inline bool buffered_hold_recording(bool continuous,bool diagnostic){return !continuous&&!diagnostic;}
constexpr int64_t plan_readable_ms=2500;
inline bool touch_hold_to_record(bool contact,bool active,bool start_target,bool same_epoch,bool painting,int64_t age){return contact&&active&&start_target&&same_epoch&&!painting&&age>=600;}
inline bool start_voice_upload(unsigned samples,bool started){return !started&&samples>=voice_min_samples;}
}
