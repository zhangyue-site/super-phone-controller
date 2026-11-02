#include "audio_policy.h"
#include <string.h>
void pc_audio_take_init(pc_audio_take *t){memset(t,0,sizeof(*t));}
bool pc_audio_take_begin(pc_audio_take *t,unsigned epoch,uint64_t now){
 if(t->active)return false;
 pc_audio_take_init(t);t->active=true;t->epoch=epoch;t->started=now;return true;
}
bool pc_audio_take_append(pc_audio_take *t,unsigned epoch,uint64_t now,size_t bytes,unsigned rms){
 if(!t->active||t->cancelled)return false;
 if(epoch!=t->epoch||now<t->started||now-t->started>10000||!bytes||bytes%2||bytes>320000-t->bytes||rms>32768){
  t->cancelled=true;return false;
 }
 t->bytes+=bytes;t->energy+=(uint64_t)rms*rms*(bytes/2);return true;
}
bool pc_audio_take_finish(const pc_audio_take *t){
 return t->active&&!t->cancelled&&t->bytes>=12800&&t->bytes<=320000&&
  t->energy>=(uint64_t)80*80*(t->bytes/2);
}
