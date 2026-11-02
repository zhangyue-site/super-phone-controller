#include "ota_engine.h"
#include <string.h>
#define COMMIT (1u<<31)
void pc_ota_init(pc_ota *o,pc_ota_hooks h,void *ctx){memset(o,0,sizeof(*o));o->hooks=h;o->ctx=ctx;atomic_init(&o->epoch,1);atomic_init(&o->state,0);atomic_init(&o->error,0);atomic_init(&o->progress,0);atomic_init(&o->reserved,false);atomic_init(&o->grant_until,0);o->worker_epoch=1;}
unsigned pc_ota_epoch(pc_ota *o){return atomic_load(&o->epoch);}
unsigned pc_ota_state(pc_ota *o){return atomic_load(&o->state);}
bool pc_ota_busy(pc_ota *o){return atomic_load(&o->reserved);}
bool pc_ota_cancel(pc_ota *o){unsigned e=pc_ota_epoch(o);atomic_store(&o->grant_until,0);while(!(e&COMMIT)){if(atomic_compare_exchange_weak(&o->epoch,&e,e+1))return true;}return false;}
void pc_ota_grant(pc_ota *o,uint64_t now){if(!pc_ota_busy(o))atomic_store(&o->grant_until,now+60000);}
static void reset(pc_ota *o,unsigned state,unsigned error){if(o->open)o->hooks.abort(o->ctx);o->open=false;o->total=o->written=0;atomic_store(&o->grant_until,0);atomic_store(&o->reserved,false);atomic_store(&o->progress,0);atomic_store(&o->error,error);atomic_store(&o->state,state);}
void pc_ota_tick(pc_ota *o,uint64_t now){unsigned e=pc_ota_epoch(o);if(e&COMMIT)return;if(e!=o->worker_epoch){reset(o,0,0);o->worker_epoch=e;}else if(o->open&&now-o->last>30000){pc_ota_cancel(o);reset(o,4,1);o->worker_epoch=pc_ota_epoch(o);}}
void pc_ota_process(pc_ota *o,unsigned epoch,const uint8_t *p,size_t n,uint64_t now){
 pc_ota_tick(o,now);if(epoch!=pc_ota_epoch(o)||(epoch&COMMIT)||!n)return;
 if(p[0]==4){pc_ota_cancel(o);pc_ota_tick(o,now);return;}
 if(p[0]==1){
  uint64_t until=atomic_exchange(&o->grant_until,0);
  if(!until||now>=until||o->open||n!=37){if(!o->open)reset(o,4,1);return;}
  uint32_t total=(uint32_t)p[1]|((uint32_t)p[2]<<8)|((uint32_t)p[3]<<16)|((uint32_t)p[4]<<24);
  if(total<4096||total>0x600000){reset(o,4,4);return;}
  atomic_store(&o->reserved,true);memcpy(o->digest,p+5,32);o->total=total;o->written=0;
  /* Mark open before begin so partial platform failures are always aborted. */
  o->open=true;if(!o->hooks.begin(o->ctx,total)){reset(o,4,3);return;}
  if(epoch!=pc_ota_epoch(o)){pc_ota_tick(o,now);return;}
  o->last=now;atomic_store(&o->error,0);atomic_store(&o->progress,0);atomic_store(&o->state,1);return;
 }
 if(!o->open||pc_ota_state(o)!=1)return;
 o->last=now;
 if(p[0]==2){
  if(n<2||n>512||n-1>o->total-o->written){reset(o,4,4);return;}
  if(!o->hooks.write(o->ctx,p+1,n-1)){reset(o,4,3);return;}
  if(epoch!=pc_ota_epoch(o)){pc_ota_tick(o,now);return;}
  o->written+=(uint32_t)n-1;atomic_store(&o->progress,(uint64_t)o->written*100/o->total);return;
 }
 if(p[0]!=3||n!=1){reset(o,4,2);return;}
 if(o->written!=o->total){reset(o,4,4);return;}
 if(o->hooks.commit_allowed&&!o->hooks.commit_allowed(o->ctx)){reset(o,4,1);return;}
 atomic_store(&o->state,2);
 if(!o->hooks.verify(o->ctx,o->digest)){reset(o,4,5);return;}
 if(o->hooks.commit_allowed&&!o->hooks.commit_allowed(o->ctx)){reset(o,4,1);return;}
 unsigned expected=epoch;
 if(!atomic_compare_exchange_strong(&o->epoch,&expected,epoch|COMMIT)){pc_ota_tick(o,now);return;}
 if(!o->hooks.commit(o->ctx)){atomic_store(&o->epoch,epoch+1);reset(o,4,3);o->worker_epoch=epoch+1;return;}
 o->open=false;atomic_store(&o->progress,100);atomic_store(&o->state,3);
 /* Keep reserved/commit latched until reset: STOP cannot undo selected boot slot. */
 o->hooks.restart(o->ctx);
}

bool pc_ota_challenge_valid(uint64_t issued,uint64_t now){return now>=issued&&now-issued<60000;}
