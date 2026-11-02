#include "audio_policy.h"
#include <assert.h>
int main(void){
 pc_audio_take t;pc_audio_take_init(&t);assert(!pc_audio_take_finish(&t));
 assert(pc_audio_take_begin(&t,7,100));assert(!pc_audio_take_begin(&t,7,100));
 assert(pc_audio_take_append(&t,7,101,512,0));
 assert(!pc_audio_take_finish(&t));
 for(unsigned i=0;i<24;i++)assert(pc_audio_take_append(&t,7,120+i*16,512,1000));
 assert(pc_audio_take_finish(&t));assert(t.bytes==12800);
 assert(!pc_audio_take_append(&t,8,600,512,1000));assert(t.cancelled);
 pc_audio_take_init(&t);assert(pc_audio_take_begin(&t,1,0));
 assert(!pc_audio_take_append(&t,1,10001,512,1000));
 pc_audio_take_init(&t);assert(pc_audio_take_begin(&t,1,0));
 for(unsigned i=0;i<625;i++)assert(pc_audio_take_append(&t,1,i*16,512,1000));
 assert(!pc_audio_take_append(&t,1,9999,512,1000));assert(t.bytes==320000);
 pc_audio_take_init(&t);assert(pc_audio_take_begin(&t,1,0));
 assert(!pc_audio_take_append(&t,1,1,511,1000));
 return 0;
}
