#include <cassert>
#include "voice_claim_admission.h"
#include "voice_lifecycle.h"
using namespace controller;
int main(){
 VoiceLifecycle life;unsigned before=life.epoch;
 // An idle network poll owns no recording lease; a held local request wins.
 assert(life.can_start());life.epoch.fetch_add(1);life.stage=4;
 assert(!admit_remote_claim(true,life.current(before),life.can_start(),true,false,false,false));
 life.stage=0;
 assert(!admit_remote_claim(true,true,true,true,false,false,false));
 assert(!admit_remote_claim(true,true,true,false,true,false,false));
 assert(!admit_remote_claim(true,true,true,false,false,true,false));
 assert(!admit_remote_claim(false,true,true,false,false,false,false));
 assert(admit_remote_claim(true,true,true,false,false,false,false));
 {VoiceLifecycle::Lease active(life);assert(!life.can_start());assert(!admit_remote_claim(true,true,life.can_start(),false,false,false,false));}
 assert(life.can_start());
}
