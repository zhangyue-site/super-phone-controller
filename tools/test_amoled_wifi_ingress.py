"""Exercise production Wi-Fi ingress against the same protected OTA engine."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
source=(root/"firmware-amoled/main/ota_ble.c").read_text()
def fn(name):
 start=source.index(name+"(");start=source.rfind("\n",0,start)+1
 brace=source.index("{",start);end=brace+1;depth=1
 while depth:
  depth+=(source[end]=="{")-(source[end]=="}");end+=1
 return source[start:end]
code=r"""
#include "ota_engine.h"
#include "version_policy.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
#include <stdatomic.h>
#define BLE_HS_CONN_HANDLE_NONE 65535
#define taskENTER_CRITICAL(p) ((void)(p))
#define taskEXIT_CRITICAL(p) ((void)(p))
#define pdMS_TO_TICKS(n) (n)
#define pdTRUE 1
static pc_ota engine;
static atomic_bool pending;static atomic_ullong wifi_deadline;
static int lock,queue,connection=BLE_HS_CONN_HANDLE_NONE;
static uint8_t grant_digest[32];static uint32_t grant_size;static char grant_version[32];
static unsigned head,tail;
static bool armed,held,queue_full;
static unsigned begins,writes,commits,aborts,restarts;
typedef struct {unsigned epoch;uint16_t length;uint8_t bytes[512];} Chunk;
static Chunk chunks[32];
static uint64_t now_ms(void){return 1000;}
static bool amoled_ota_ready(void){return true;}
static bool amoled_ota_busy(void){return atomic_load(&pending)||pc_ota_busy(&engine);}
typedef struct {char version[32];} App;
static const App *esp_app_get_description(void){static App app={"0.3.0-amoled"};return &app;}
static bool amoled_usb_reserve_ota(bool (*callback)(void)){
 if(held||armed)return false;held=true;bool ok=callback();held=false;return ok;
}
static int xQueueSend(int q,const Chunk *c,int ticks){
 (void)q;(void)ticks;if(queue_full)return 0;assert(tail<32);chunks[tail++]=*c;return pdTRUE;
}
static bool begin(void *ctx,uint32_t total){(void)ctx;assert(total==grant_size&&total==4096);assert(!strcmp(grant_version,"0.3.1-amoled"));assert(!memcmp(grant_digest,engine.digest,32));begins++;return true;}
static bool write_image(void *ctx,const uint8_t *p,size_t n){(void)ctx;assert(p&&n);writes++;return true;}
static bool verify(void *ctx,const uint8_t sha[32]){(void)ctx;return !memcmp(sha,grant_digest,32);}
static bool commit(void *ctx){(void)ctx;commits++;return true;}
static void abort_image(void *ctx){(void)ctx;aborts++;}
static void restart(void *ctx){(void)ctx;restarts++;}
static void pump(void){
 while(head<tail){Chunk *c=&chunks[head++];pc_ota_process(&engine,c->epoch,c->bytes,c->length,now_ms());if(!pc_ota_busy(&engine))atomic_store(&pending,false);}
}
static void reset(void){
 pc_ota_init(&engine,(pc_ota_hooks){begin,write_image,verify,commit,abort_image,restart,NULL},NULL);
 atomic_store(&pending,false);connection=BLE_HS_CONN_HANDLE_NONE;armed=held=queue_full=false;
 head=tail=begins=writes=commits=aborts=restarts=0;
}
"""
code+="\n".join(fn(n) for n in ["authorized_release_version","reserve_input","amoled_ota_wifi_live","amoled_ota_wifi_begin","amoled_ota_wifi_chunk"])
code+=r"""
int main(void){
 uint8_t digest[32]={7},bytes[511]={0};unsigned epoch=0;
 reset();connection=1;assert(!amoled_ota_wifi_begin("0.3.1-amoled",4096,digest,121000,&epoch));assert(!tail&&!pending);
 reset();armed=true;assert(!amoled_ota_wifi_begin("0.3.1-amoled",4096,digest,121000,&epoch));assert(!pending);
 reset();held=true;assert(!amoled_ota_wifi_begin("0.3.1-amoled",4096,digest,121000,&epoch));
 reset();assert(amoled_ota_wifi_begin("0.3.0-amoled",4096,digest,121000,&epoch));reset();assert(amoled_ota_wifi_begin("0.2.0-amoled",4096,digest,121000,&epoch));reset();assert(!amoled_ota_wifi_begin("0.3.1-amoled",0x600001,digest,121000,&epoch));
 reset();queue_full=true;assert(!amoled_ota_wifi_begin("0.3.1-amoled",4096,digest,121000,&epoch));assert(!pending);
 reset();assert(amoled_ota_wifi_begin("0.3.1-amoled",4096,digest,121000,&epoch));assert(pending);
 assert(!amoled_ota_wifi_begin("0.3.1-amoled",4096,digest,121000,&epoch));
 assert(!amoled_ota_wifi_chunk(epoch,bytes,512,false));
 assert(pc_ota_cancel(&engine));pump();assert(!begins&&!pc_ota_busy(&engine)&&!pending);
 assert(!amoled_ota_wifi_chunk(epoch,bytes,1,false));
 reset();assert(amoled_ota_wifi_begin("0.3.1-amoled",4096,digest,121000,&epoch));pump();assert(begins==1);
 assert(pc_ota_cancel(&engine));assert(!amoled_ota_wifi_chunk(epoch,bytes,1,false));pc_ota_tick(&engine,now_ms());
 assert(aborts==1&&!pc_ota_busy(&engine));
 reset();assert(amoled_ota_wifi_begin("0.3.1-amoled",4096,digest,121000,&epoch));pump();
 for(unsigned offset=0;offset<4096;){unsigned n=4096-offset;if(n>511)n=511;assert(amoled_ota_wifi_chunk(epoch,bytes,n,false));pump();offset+=n;}
 assert(amoled_ota_wifi_chunk(epoch,NULL,0,true));pump();
 assert(commits==1&&restarts==1&&!aborts&&pc_ota_state(&engine)==3&&pc_ota_busy(&engine));
 assert(!pc_ota_cancel(&engine));assert(!amoled_ota_wifi_begin("0.3.1-amoled",4096,digest,121000,&epoch));
 puts("Production Wi-Fi ingress: BLE/ARM/USB mutex, single writer, epoch cancel, bounded chunks and commit passed");
}
"""
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/"test.c").write_text(code)
 subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror","-Wno-misleading-indentation","-fsanitize=address,undefined","-g","-I",str(root/"firmware-amoled/main"),str(p/"test.c"),str(root/"firmware-amoled/main/ota_engine.c"),"-o",str(p/"test")],check=True)
 subprocess.run([str(p/"test")],check=True)

