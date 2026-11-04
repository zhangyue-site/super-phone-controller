"""Run the production Wi-Fi download adapter against a bounded fake TLS server."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
source=(root/"firmware-amoled/main/wifi.c").read_text()
def function(name):
 start=source.index(name+"(");start=source.rfind("\n",0,start)+1
 brace=source.index("{",start);end=brace+1;depth=1
 while depth:
  depth+=(source[end]=="{")-(source[end]=="}");end+=1
 return source[start:end]
code=r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdatomic.h>
#include <string.h>
#include <stdio.h>
#include <time.h>
#include "wifi_policy.h"
#include "version_policy.h"
static bool automatic_download;
typedef struct {char version[32];} App;
static const App *esp_app_get_description(void){static App app={"0.3.0-amoled"};return &app;}
#define ESP_OK 0
#define pdMS_TO_TICKS(n) (n)
#define WIFI_PS_NONE 0
#define WIFI_PS_MIN_MODEM 1
static int esp_wifi_set_ps(int ps){(void)ps;return 0;}
typedef struct Client {int kind,used;} Client;
typedef Client *esp_http_client_handle_t;
typedef struct {
 const char *url;int timeout_ms,buffer_size;
 void *crt_bundle_attach;bool disable_auto_redirect,keep_alive_enable;
} esp_http_client_config_t;
static atomic_uint generation=1,stage,received_bytes,image_bytes;
static atomic_bool connected=true,transfer=true;
static int status_code=200,content_mode,read_mode,queue_mode;
static int opened,closed,auth_calls,begins,finishes,cancels,chunks,read_calls;
static unsigned bytes;
static bool ble,finalized,ota_valid=true,certificate_ok=true,clock_valid=true,stalled=false;
static int64_t clock_us=1000;
static char manifest[193];
static uint8_t image[4096];
static Client clients[2];
static int bundle;
#define esp_crt_bundle_attach (&bundle)
static int64_t esp_timer_get_time(void){return clock_us;}
static time_t fake_time(time_t *out){(void)out;return clock_valid?1800000000:0;}
#define time fake_time
static bool amoled_relay_connected(void){return ble;}
static esp_http_client_handle_t esp_http_client_init(const esp_http_client_config_t *cfg){
 assert(cfg->disable_auto_redirect&&cfg->crt_bundle_attach==esp_crt_bundle_attach);
 assert(cfg->timeout_ms==5000&&cfg->buffer_size==2048&&!cfg->keep_alive_enable);
 assert(!strncmp(cfg->url,"https://controller.test/firmware/",strlen("https://controller.test/firmware/")));
 assert(opened<2);Client *c=clients+opened++;c->kind=opened-1;c->used=0;return c;
}
static int amoled_identity_http_auth(esp_http_client_handle_t c){(void)c;auth_calls++;return ESP_OK;}
static int esp_http_client_set_header(esp_http_client_handle_t c,const char *name,const char *value){
 (void)c;assert(!strcmp(name,"Connection")&&!strcmp(value,"close"));return ESP_OK;
}
static int esp_http_client_open(esp_http_client_handle_t c,int n){(void)c;(void)n;return certificate_ok?ESP_OK:-1;}
static int64_t esp_http_client_fetch_headers(esp_http_client_handle_t c){
 if(content_mode==1)return 0x600001;
 if(content_mode==2)return -1;
 if(content_mode==3&&c->kind==0)return 193;
 if(content_mode==4&&c->kind==1)return sizeof(image)-1;
 return c->kind?sizeof(image):strlen(manifest);
}
static int esp_http_client_get_status_code(esp_http_client_handle_t c){(void)c;return status_code;}
static bool esp_http_client_is_chunked_response(esp_http_client_handle_t c){(void)c;return content_mode==5;}
static void esp_http_client_close(esp_http_client_handle_t c){(void)c;closed++;}
static void esp_http_client_cleanup(esp_http_client_handle_t c){(void)c;}
static int esp_http_client_read(esp_http_client_handle_t c,char *out,int n){
 read_calls++;
 if(read_mode==1&&c->kind==1)return -1;
 if(read_mode==2&&c->kind==1)return 0;
 if(read_mode==3&&c->kind==1)atomic_fetch_add(&generation,1);
 if(read_mode==4&&c->kind==1)atomic_store(&connected,false);
 if(read_mode==5&&c->kind==1)clock_us+=601000000;
 if(read_mode==6&&c->kind==1)ble=true;
 const uint8_t *data=c->kind?image:(const uint8_t*)manifest;
 int size=c->kind?(int)sizeof(image):(int)strlen(manifest),left=size-c->used;
 if(n>left)n=left;
 if(n>127)n=127; /* Real transport may split either response arbitrarily. */
 memcpy(out,data+c->used,n);c->used+=n;return n;
}
static bool esp_http_client_is_complete_data_received(esp_http_client_handle_t c){
 return c->used==(c->kind?(int)sizeof(image):(int)strlen(manifest));
}
static bool amoled_unhex(const char *s,size_t n,uint8_t *out){
 if(n!=32||strlen(s)!=64)return false;
 memset(out,0,n);return true;
}
static bool amoled_ota_wifi_begin(const char *v,uint32_t n,const uint8_t digest[32],uint64_t deadline,unsigned *epoch){
 assert(deadline==600001);assert(!strcmp(v,"0.3.1-amoled")&&n==4096&&digest);begins++;*epoch=1;return true;
}
static bool amoled_ota_wifi_live(unsigned epoch){return epoch==1&&ota_valid&&!finalized;}
static bool amoled_ota_wifi_chunk(unsigned epoch,const uint8_t *data,size_t n,bool final){
 assert(epoch==1);if(queue_mode==1)return false;
 if(final){assert(!data&&!n);finishes++;finalized=true;}
 else {assert(data&&n&&n<=511);chunks++;bytes+=n;if(queue_mode==2&&bytes==4096)clock_us+=601000000;}
 return true;
}
static void amoled_ota_status(uint8_t out[4]){memset(out,0,4);out[0]=finalized?3:1;}
static void amoled_ota_cancel(void){cancels++;ota_valid=false;}
static void vTaskDelay(int ticks){clock_us+=(int64_t)ticks*1000;}
"""
code+="\n".join(function(n) for n in ["live","close_http","open_http","download"])
code+=r"""
static void reset(void){
 atomic_store(&generation,1);atomic_store(&stage,0);atomic_store(&connected,true);
 opened=closed=auth_calls=begins=finishes=cancels=chunks=read_calls=0;bytes=0;
 status_code=200;content_mode=read_mode=queue_mode=0;ble=finalized=false;
 ota_valid=certificate_ok=clock_valid=true;clock_us=1000;
 strcpy(manifest,"PCOTA1\n4096\n0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n0.3.1-amoled\n");
}
int main(void){
 reset();automatic_download=true;
 strcpy(manifest,"PCOTA1\n4096\n0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n0.3.0-amoled\n");
 download("https://controller.test",1);assert(!begins&&opened==1&&closed==1&&atomic_load(&stage)==0);
 reset();strcpy(manifest,"PCOTA1\n4096\n0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n0.2.9-amoled\n");
 download("https://controller.test",1);assert(!begins&&atomic_load(&stage)==0);
 automatic_download=false;
 reset();download("https://controller.test",1);
 assert(bytes==4096&&begins==1&&finishes==1&&!cancels&&opened==2&&closed==2&&auth_calls==2);
 for(int mode=1;mode<=5;mode++){
  reset();content_mode=mode;download("https://controller.test",1);
  assert(!finishes&&atomic_load(&stage)==4&&opened==closed);
 }
 for(int mode=1;mode<=5;mode++){
  reset();read_mode=mode;download("https://controller.test",1);
  assert(!finishes&&cancels==1&&bytes==0&&opened==closed);
 }
 reset();status_code=302;download("https://controller.test",1);assert(!begins&&opened==1&&closed==1);
 reset();certificate_ok=false;download("https://controller.test",1);assert(!begins&&opened==1&&closed==1);
 reset();clock_valid=false;download("https://controller.test",1);assert(!opened&&!begins);
 reset();queue_mode=2;download("https://controller.test",1);assert(!finishes&&cancels==1);
 reset();queue_mode=1;download("https://controller.test",1);assert(!finishes&&cancels==1&&bytes==0);
 reset();manifest[10]='x';download("https://controller.test",1);assert(!begins&&opened==1);
 reset();atomic_store(&generation,2);download("https://controller.test",1);assert(!opened&&!begins);
 reset();read_mode=6;download("https://controller.test",1);assert(finishes==1&&!cancels);
 reset();ble=true;atomic_store(&transfer,false);download("https://controller.test",1);assert(!opened&&!begins);
 puts("Production Wi-Fi TLS/redirect/bounds/partial-read/STOP/disconnect/deadline/queue adapter passed");
}
"""
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/"test.c").write_text(code)
 subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror","-Wno-unused-variable","-fsanitize=address,undefined","-g","-I",str(root/"firmware-amoled/main"),str(p/"test.c"),str(root/"firmware-amoled/main/wifi_policy.c"),"-o",str(p/"test")],check=True)
 subprocess.run([str(p/"test")],check=True)

