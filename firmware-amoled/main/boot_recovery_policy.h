#pragma once
#include <stdbool.h>
#include <stdint.h>
#define AMOLED_RECOVERY_MAGIC UINT32_C(0x414d5231)
#define AMOLED_CRASH_LIMIT 3u
#define AMOLED_HEALTHY_MS 30000u
static inline unsigned amoled_boot_crashes(bool valid,unsigned previous,bool crash_reset){
 if(!crash_reset)return 0;
 if(!valid||previous>AMOLED_CRASH_LIMIT)previous=0;
 return previous<AMOLED_CRASH_LIMIT?previous+1:AMOLED_CRASH_LIMIT;
}
static inline bool amoled_recovery_required(unsigned crashes){return crashes>=AMOLED_CRASH_LIMIT;}
static inline bool amoled_boot_healthy(uint64_t uptime_ms){return uptime_ms>=AMOLED_HEALTHY_MS;}
