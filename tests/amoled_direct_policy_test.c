#include "direct_policy.h"
#include <assert.h>
#include <string.h>
int main(void){
 pc_direct d;pc_direct_init(&d);unsigned epoch=d.epoch;
 char lease[65];memset(lease,'b',64);lease[64]=0;
 const char *task="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",*id="cccccccccccccccccccccccccccccccc";
 assert(!pc_direct_claim_ready(&d,true,true,false,false));
 assert(pc_direct_lease(&d,lease));
 assert(!pc_direct_begin(&d,task,100,true,true,true,false));
 assert(pc_direct_begin(&d,task,100,true,true,false,false));
 assert(!pc_direct_reserve(&d,id,101,false,true,false,false));
 assert(!d.running);assert(pc_direct_lease(&d,lease));assert(pc_direct_begin(&d,task,100,true,true,false,false));
 assert(pc_direct_reserve(&d,id,101,true,true,false,false));
 assert(!pc_direct_reserve(&d,id,102,true,true,false,false));
 pc_direct_cancel(&d);assert(d.epoch!=epoch&&!d.running&&!d.lease[0]);
 assert(!pc_direct_reserve(&d,"dddddddddddddddddddddddddddddddd",103,true,true,false,false));
 assert(pc_direct_lease(&d,lease));assert(pc_direct_begin(&d,task,200,true,true,false,false));
 assert(!pc_direct_reserve(&d,id,180200,true,true,false,false));
 assert(!d.running);
 assert(pc_direct_lease(&d,lease));assert(pc_direct_begin(&d,task,300,true,true,false,false));
 assert(!pc_direct_reserve(&d,id,301,true,true,true,false));assert(!d.running);
 assert(!pc_direct_lease(&d,"bad"));
 return 0;
}
