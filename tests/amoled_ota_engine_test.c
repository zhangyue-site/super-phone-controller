#include "ota_engine.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned begins,writes,aborts,commits,restarts;static bool hash_ok=true,commit_ok=true,cancel_verify=false;static pc_ota *active;
static bool begin(void *ctx,uint32_t n){begins++;return n<=0x600000;}
static bool write_data(void *ctx,const uint8_t *p,size_t n){writes++;return true;}
static bool verify(void *ctx,const uint8_t digest[32]){if(cancel_verify)pc_ota_cancel(active);return hash_ok;}
static bool commit(void *ctx){commits++;return commit_ok;}
static void abort_image(void *ctx){aborts++;}
static void restart(void *ctx){restarts++;}
static pc_ota_hooks hooks={begin,write_data,verify,commit,abort_image,restart};
static uint8_t b[37]={1,0,16};static uint8_t data[512]={2};
static void setup(pc_ota *o){begins=writes=aborts=commits=restarts=0;hash_ok=commit_ok=true;cancel_verify=false;pc_ota_init(o,hooks,0);active=o;}
static void send(pc_ota *o,const uint8_t *p,size_t n,uint64_t now){pc_ota_process(o,pc_ota_epoch(o),p,n,now);}
static void start(pc_ota *o){pc_ota_grant(o,100);send(o,b,sizeof(b),101);assert(pc_ota_state(o)==1);}
static void fill(pc_ota *o){for(int i=0;i<8;i++)send(o,data,512,102+i);send(o,data,9,111);}
int main(void){pc_ota o;
 assert(pc_ota_challenge_valid(100,101));assert(!pc_ota_challenge_valid(100,60100));assert(!pc_ota_challenge_valid(100,99));
 setup(&o);send(&o,b,37,100);assert(begins==0&&commits==0);
 setup(&o);pc_ota_grant(&o,1);send(&o,b,37,60002);assert(begins==0);
 setup(&o);start(&o);fill(&o);uint8_t end=3;send(&o,&end,1,112);assert(pc_ota_state(&o)==3&&commits==1&&restarts==1);
 setup(&o);start(&o);send(&o,&end,1,112);assert(commits==0&&pc_ota_state(&o)==4);
 setup(&o);start(&o);fill(&o);hash_ok=false;send(&o,&end,1,112);assert(commits==0&&aborts==1);
 setup(&o);start(&o);fill(&o);cancel_verify=true;send(&o,&end,1,112);assert(commits==0&&restarts==0&&aborts==1);
 setup(&o);start(&o);unsigned old=pc_ota_epoch(&o);pc_ota_cancel(&o);pc_ota_process(&o,old,data,512,103);assert(writes==0&&aborts==1);
 setup(&o);start(&o);pc_ota_tick(&o,30102);assert(aborts==1&&commits==0);
 setup(&o);start(&o);fill(&o);commit_ok=false;send(&o,&end,1,112);assert(commits==1&&restarts==0&&pc_ota_state(&o)==4);
 setup(&o);start(&o);fill(&o);send(&o,data,2,112);assert(commits==0&&aborts==1);
 setup(&o);pc_ota_grant(&o,100);uint8_t huge[37]={1,1,0,96};send(&o,huge,37,101);assert(begins==0);
 setup(&o);pc_ota_grant(&o,100);send(&o,b,36,101);assert(begins==0);send(&o,b,37,102);assert(begins==0); /* bad BEGIN consumes grant */
 setup(&o);start(&o);uint8_t stop=4;send(&o,&stop,1,102);assert(aborts==1&&!pc_ota_busy(&o));send(&o,b,37,103);assert(begins==1);
 puts("AMOLED OTA lifecycle: auth expiry, ordered transfer, bounds, hash, cancel, timeout and commit passed");
}
