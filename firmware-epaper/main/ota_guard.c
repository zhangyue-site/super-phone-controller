#include "ota_guard.h"
#include <stdatomic.h>
static atomic_uint state;
enum { CANCEL=4, COMMIT=8 };
bool ota_guard_acquire(unsigned o){unsigned expected=0;return atomic_compare_exchange_strong(&state,&expected,o);}
void ota_guard_cancel(unsigned o){unsigned s=atomic_load(&state);while((s&3)==o && !(s&COMMIT) && !atomic_compare_exchange_weak(&state,&s,s|CANCEL)) {}}
bool ota_guard_cancelled(unsigned o){return atomic_load(&state)!=o;}
bool ota_guard_commit(unsigned o){unsigned expected=o;return atomic_compare_exchange_strong(&state,&expected,o|COMMIT);}
void ota_guard_release(unsigned o){unsigned s=atomic_load(&state);while((s&3)==o && !atomic_compare_exchange_weak(&state,&s,0)) {}}

enum ota_guard_phase ota_guard_get_phase(void){unsigned s=atomic_load(&state);if(!s)return OTA_GUARD_IDLE;if((s&3)==OTA_POWER)return OTA_GUARD_POWER;return (s&COMMIT)?OTA_GUARD_COMMIT:OTA_GUARD_WRITING;}
