"""Execute production recorder lifecycle with synthetic PCM and hardware/network mocks."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
source=(root/"firmware-amoled/main/audio.c").read_text()
def fn(name):
 start=source.index(name+"(");start=source.rfind("\n",0,start)+1
 brace=source.index("{",start);end=brace+1;depth=1
 while depth:
  depth+=(source[end]=="{")-(source[end]=="}");end+=1
 return source[start:end]
code=r"""
#include "audio_policy.h"
#include <stdatomic.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>
#include <assert.h>
#include <stdio.h>
#define ESP_CODEC_DEV_OK 0
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_8BIT 2
#define pdPASS 1
static atomic_bool held,busy;
static atomic_uint generation=1,stage,duration;
static void *microphone=(void *)1;
static bool wifi=true,owner,ble,ota,armed,identity=true,codec_ok=true,heap_ok=true;
static int reads,closes,uploads,stops,amp_off,zero_frees,mode;
static uint64_t clock_us=1000;
static void (*scheduled)(void *);
static void clear_result(void){}
static void amoled_audio_cancel(void);
static int64_t esp_timer_get_time(void){return clock_us;}
static bool amoled_wifi_connected(void){return wifi;}
static bool amoled_relay_audio_owned(void){return owner;}
static bool amoled_relay_connected(void){return ble;}
static bool amoled_ota_busy(void){return ota;}
static bool amoled_usb_armed(void){return armed;}
static bool amoled_identity_ready(void){return identity;}
static bool amoled_relay_audio_acquire(void){if(ble||owner)return false;owner=true;return true;}
static void amoled_relay_audio_release(void){owner=false;}
static bool amoled_usb_reserve_ota(bool (*callback)(void)){return !armed&&!ota&&callback();}
static bool amplifier_off(void){amp_off++;return true;}
static bool microphone_open(void){return codec_ok;}
static void esp_fill_random(void *out,size_t n){memset(out,1,n);}
static void amoled_hex(const uint8_t *in,size_t n,char *out){(void)in;memset(out,'a',n*2);out[n*2]=0;}
static void *heap_caps_malloc(size_t n,int caps){assert(n==320000&&caps==3);return heap_ok?malloc(n):NULL;}
static void heap_caps_free(void *p){
 for(unsigned i=0;i<320000;i++)assert(!((uint8_t *)p)[i]);
 zero_frees++;free(p);
}
static int esp_codec_dev_read(void *mic,void *out,int size){
 assert(mic&&size==512);reads++;clock_us+=16000;
 int16_t *p=out;for(int i=0;i<size/2;i++)p[i]=mode==1?0:1000;
 if(reads==26)held=false;
 if(mode==2&&reads==10)amoled_audio_cancel();
 if(mode==3&&reads==10){wifi=false;amoled_audio_cancel();}
 if(mode==4&&reads==1)clock_us+=11000000;
 if(mode==5&&reads==1)held=false;
 if(mode==6&&reads==25)held=false;
 return ESP_CODEC_DEV_OK;
}
static void esp_codec_dev_close(void *mic){assert(mic);closes++;}
static bool upload(const uint8_t *pcm,size_t size,unsigned epoch,const char *session,bool stop){
 assert(strlen(session)==16);assert(closes||!reads);
 if(stop){stops++;assert(!pcm&&!size);return true;}
 assert(pcm&&size==12800&&atomic_load(&generation)==epoch);
 uploads++;return true;
}
static void vTaskDelete(void *p){assert(!p);}
static int xTaskCreate(void (*task)(void *),const char *name,unsigned stack,void *ctx,int priority,void *out){
 (void)name;(void)ctx;(void)priority;(void)out;assert(stack==8192);scheduled=task;return pdPASS;
}
"""
code+="\n".join(fn(n) for n in ["amoled_audio_cancel","amoled_audio_release","live","recorder","reserve_audio","amoled_audio_press"])
# Production cancel calls the public busy getter.
code=code.replace('static void amoled_audio_cancel(void);','static void amoled_audio_cancel(void);\nstatic bool amoled_audio_busy(void){return busy;}')
code+=r"""
static void reset(void){
 held=busy=false;generation=1;stage=duration=0;
 wifi=identity=codec_ok=heap_ok=true;owner=ble=ota=armed=false;
 reads=closes=uploads=stops=amp_off=zero_frees=mode=0;clock_us=1000;scheduled=NULL;
}
int main(void){
 reset();assert(!scheduled&&!reads); /* No task/microphone exists before PRESS. */
 assert(amoled_audio_press());assert(scheduled&&owner&&!reads);
 assert(!amoled_audio_press());scheduled(NULL);
 assert(reads==26&&uploads==1&&closes==1&&zero_frees==1&&!owner&&!busy&&stage==3);
 reset();mode=5;assert(amoled_audio_press());scheduled(NULL);assert(reads==1&&!uploads&&duration==0&&stage==4);
 reset();mode=6;assert(amoled_audio_press());scheduled(NULL);assert(reads==25&&!uploads&&duration==384&&stage==4);
 reset();mode=1;assert(amoled_audio_press());scheduled(NULL);assert(!uploads&&stage==4&&closes==1);
 reset();mode=2;assert(amoled_audio_press());scheduled(NULL);assert(reads==10&&!uploads&&stops==1&&stage==5&&!owner);
 reset();mode=3;assert(amoled_audio_press());scheduled(NULL);assert(!uploads&&stops==1&&!owner);
 reset();mode=4;assert(amoled_audio_press());scheduled(NULL);assert(!uploads&&reads==1&&closes==1&&stage==4);
 reset();assert(amoled_audio_press());amoled_audio_release();scheduled(NULL);assert(!reads&&!uploads&&zero_frees==1&&!owner);
 reset();heap_ok=false;assert(amoled_audio_press());scheduled(NULL);assert(!reads&&!uploads&&!owner&&stage==4);
 reset();codec_ok=false;assert(amoled_audio_press());scheduled(NULL);assert(!reads&&!uploads&&zero_frees==1&&!owner);
 reset();ble=true;assert(!amoled_audio_press());assert(!busy&&!scheduled);
 reset();ota=true;assert(!amoled_audio_press());assert(!busy&&!scheduled);
 reset();armed=true;assert(!amoled_audio_press());assert(!busy&&!scheduled);
 puts("Production recorder: explicit PRESS, real PCM bounds, RELEASE, silence, STOP/late read, network, timeout, zeroization and owner release passed");
}
"""
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/"test.c").write_text(code)
 subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror","-Wno-unused-parameter","-fsanitize=address,undefined","-I",str(root/"firmware-amoled/main"),str(p/"test.c"),str(root/"firmware-amoled/main/audio_policy.c"),"-lm","-o",str(p/"test")],check=True)
 subprocess.run([str(p/"test")],check=True)

