"""Run the production voice HTTPS + codec lifecycle with bounded fake I/O."""
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[1]
source=(r/'firmware-amoled/main/companion_speech.c').read_text()
source='\n'.join(x for x in source.splitlines() if not x.startswith('#include'))
stub=r"""
#include "companion_speech.h"
#include "cJSON.h"
#include <assert.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#define ESP_OK 0
#define ESP_CODEC_DEV_OK 0
typedef int wifi_ps_type_t;
enum {WIFI_PS_NONE,WIFI_PS_MIN_MODEM};
static wifi_ps_type_t ps=WIFI_PS_MIN_MODEM;
static int esp_wifi_get_ps(wifi_ps_type_t *p){*p=ps;return 0;}
static int esp_wifi_set_ps(wifi_ps_type_t p){ps=p;return 0;}
#define BSP_POWER_AMP_IO 1
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_8BIT 2
#define portMUX_INITIALIZER_UNLOCKED 0
#define taskENTER_CRITICAL(p) ((void)(p))
#define taskEXIT_CRITICAL(p) ((void)(p))
#define pdMS_TO_TICKS(n) (n)
typedef int portMUX_TYPE;
typedef void *esp_codec_dev_handle_t;
typedef struct {int sample_rate,channel,bits_per_sample;} esp_codec_dev_sample_info_t;
typedef struct {const char *url;int timeout_ms,buffer_size;void *crt_bundle_attach;bool disable_auto_redirect,keep_alive_enable;} esp_http_client_config_t;
typedef struct {char path[256];const char *body;size_t used,length;bool chunked;} client;
typedef client *esp_http_client_handle_t;
enum {HTTP_METHOD_GET,HTTP_METHOD_POST};
static void *esp_crt_bundle_attach;
static int mode,amp,mute=1,volume,opened,closed,played,stops,writes;
static bool alive=true;
static int64_t clock_us=1000;
static int64_t esp_timer_get_time(void){return clock_us;}
static void vTaskDelay(int n){clock_us+=(int64_t)n*1000;}
static bool amoled_wifi_connected(void){return true;}
static bool amoled_wifi_endpoint(char *s,size_t n){snprintf(s,n,"https://trusted.test");return true;}
static int amoled_identity_http_auth(void *c){return c?0:1;}
static void *heap_caps_malloc(size_t n,int caps){(void)caps;return malloc(n);}
static void heap_caps_free(void *p){free(p);}
static bool live(uint32_t e){return e==7&&alive;}
static client *esp_http_client_init(const esp_http_client_config_t *cfg){
 assert(cfg->disable_auto_redirect&&!cfg->keep_alive_enable);
 client *c=calloc(1,sizeof(*c));snprintf(c->path,sizeof(c->path),"%s",cfg->url);return c;
}
static void esp_http_client_set_method(client *c,int m){(void)c;(void)m;}
static void esp_http_client_set_header(client *c,const char *k,const char *v){
 (void)c;if(!strcmp(k,"X-Voice-Session"))assert(!strcmp(v,"aaaaaaaaaaaaaaaa"));
}
static int esp_http_client_open(client *c,size_t n){
 (void)n;
 const char *ready="{\"session\":\"aaaaaaaaaaaaaaaa\",\"sequence\":1,\"state\":\"ready\",\"recognizedText\":\"你好\",\"reply\":\"我在呢\",\"audioBytes\":6}";
 static char large_ready[512];static char audio_data[65536];
 c->body=ready;c->length=strlen(ready);
 if(mode==5){snprintf(large_ready,sizeof(large_ready),"{\"session\":\"aaaaaaaaaaaaaaaa\",\"sequence\":1,\"state\":\"ready\",\"audioBytes\":65536}");c->body=large_ready;c->length=strlen(large_ready);}
 if(strstr(c->path,"/stop"))stops++;
 if(strstr(c->path,"/played"))played++;
 if(strstr(c->path,"/audio")){
  c->body=mode==5?audio_data:"123456";c->length=mode==5?65536:6;c->chunked=mode==4;
 }
 if(mode==1&&!strstr(c->path,"/stop")){c->body="{\"session\":\"aaaaaaaaaaaaaaaa\",\"sequence\":2}";c->length=strlen(c->body);}
 return ESP_OK;
}
static int esp_http_client_write(client *c,const char *p,int n){(void)c;assert(p);return n;}
static int64_t esp_http_client_fetch_headers(client *c){return c->length;}
static int esp_http_client_get_status_code(client *c){(void)c;return 200;}
static bool esp_http_client_is_chunked_response(client *c){return c->chunked;}
static int esp_http_client_read(client *c,char *out,int n){
 assert(n<=4096);if(strstr(c->path,"/audio"))assert(ps==WIFI_PS_NONE);if(mode==5&&strstr(c->path,"/audio")){if(c->used)assert(writes>1);clock_us+=2000000;}
 if(mode==2&&strstr(c->path,"/status"))alive=false;
 if((size_t)n>c->length-c->used)n=c->length-c->used;
 memcpy(out,c->body+c->used,n);c->used+=n;return n;
}
static bool esp_http_client_is_complete_data_received(client *c){return c->used==c->length;}
static void esp_http_client_close(client *c){(void)c;}
static void esp_http_client_cleanup(client *c){free(c);}
static int gpio_set_level(int pin,int value){assert(pin==1);amp=value;return 0;}
static void *bsp_audio_codec_speaker_init(void){assert(!amp);return (void *)1;}
static int esp_codec_dev_open(void *s,esp_codec_dev_sample_info_t *f){assert(s&&!amp&&f->sample_rate==16000&&f->bits_per_sample==16&&f->channel==1);opened++;return 0;}
static int esp_codec_dev_set_out_mute(void *s,bool value){assert(s);mute=value;return 0;}
static int esp_codec_dev_set_out_vol(void *s,int value){assert(s);volume=value;return 0;}
static int esp_codec_dev_write(void *s,void *pcm,int n){
 assert(s&&pcm);writes++;
 if(n==512){assert(!amp&&mute&&!volume);return 0;}
 assert(amp&&!mute&&volume==70&&n>0&&n<=1024&&n%2==0);
 if(mode==3){alive=false;return 1;}
 return 0;
}
static int esp_codec_dev_close(void *s){assert(s&&!amp&&mute&&!volume);closed++;return 0;}
"""
test=r"""
int main(void){
 const uint8_t pcm[12800]={0};
 for(mode=0;mode<6;mode++){
  alive=true;amp=opened=closed=played=stops=writes=0;mute=1;volume=0;
  companion_speech_reset();
  bool ok=companion_speech_run(pcm,sizeof(pcm),7,"aaaaaaaaaaaaaaaa",live);
  companion_speech_state result;companion_speech_snapshot(&result);
  assert(!amp&&ps==WIFI_PS_MIN_MODEM);
  if(mode==0||mode==5){printf("mode=%d ok=%d stage=%u opened=%d closed=%d writes=%d played=%d stops=%d time=%lld\n",mode,ok,result.stage,opened,closed,writes,played,stops,(long long)clock_us);fflush(stdout);assert(ok&&result.stage==7&&opened==1&&closed==1&&writes==(mode==5?65:2)&&played==1&&!stops);}
  else{assert(!ok&&stops==1&&!played);assert(result.stage==8||result.stage==9);}
  if(opened)assert(closed==1&&mute&&!volume);
 }
 puts("Production voice: bound nonce/sequence, strict audio framing, completed-only playback, STOP/late response, codec cleanup and PA-off passed");
}
"""
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(stub+source+test)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(r/'firmware-amoled/main'),'-I',str(r/'evidence/cjson'),str(p/'test.c'),str(r/'evidence/cjson/cJSON.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
