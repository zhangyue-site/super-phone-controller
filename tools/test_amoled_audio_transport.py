"""Production audio HTTPS adapter: fake transport and real cJSON; no real API."""
from pathlib import Path
import argparse,subprocess,tempfile
root=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument("--cjson-dir",required=True);args=ap.parse_args();deps=Path(args.cjson_dir)
source=(root/"firmware-amoled/main/audio.c").read_text()
def fn(name):
 start=source.index(name+"(");start=source.rfind("\n",0,start)+1
 brace=source.index("{",start);end=brace+1;depth=1
 while depth:
  depth+=(source[end]=="{")-(source[end]=="}");end+=1
 return source[start:end]
code=r"""
#include "cJSON.h"

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <time.h>
#define ESP_OK 0
typedef void *esp_http_client_handle_t;
typedef struct {const char *url;int timeout_ms,buffer_size;void *crt_bundle_attach;bool disable_auto_redirect,keep_alive_enable;} esp_http_client_config_t;
static char session[17]="aaaaaaaaaaaaaaaa";static int64_t clock_us=1000;
static int64_t esp_timer_get_time(void){return clock_us;}
static int status_code=200,declared=-1,used,reads,opens,closes,writes,header_lease;
static bool alive=true,connected=true,tls_ok=true,chunked,cancel_read,clock_ok=true;
static const char *response="{\"recognized\":true,\"recognizedText\":\"本次文字\",\"session\":\"aaaaaaaaaaaaaaaa\",\"sequence\":1}";
static int bundle,result_lock;
static char recognized_text[481];
static unsigned generation=7;
#define taskENTER_CRITICAL(p) ((void)(p))
#define taskEXIT_CRITICAL(p) ((void)(p))
#define atomic_load(p) (*(p))
#define esp_crt_bundle_attach (&bundle)
static bool live(uint32_t epoch){return epoch==7&&alive;}
static bool amoled_wifi_connected(void){return connected;}
static bool amoled_wifi_endpoint(char *out,size_t capacity){assert(capacity>=191);strcpy(out,"https://controller.test");return true;}
static time_t fake_time(time_t *out){(void)out;return clock_ok?1800000000:0;}
#define time fake_time
static esp_http_client_handle_t esp_http_client_init(const esp_http_client_config_t *cfg){
 assert(cfg->disable_auto_redirect&&cfg->crt_bundle_attach==&bundle&&(cfg->timeout_ms==2000||cfg->timeout_ms==5000));
 assert(!strncmp(cfg->url,"https://controller.test/",strlen("https://controller.test/")));return &bundle;
}
static int amoled_identity_http_auth(esp_http_client_handle_t c){assert(c);return ESP_OK;}
#define HTTP_METHOD_POST 1
static void esp_http_client_set_method(esp_http_client_handle_t c,int method){assert(c&&method==1);}
static void esp_http_client_set_header(esp_http_client_handle_t c,const char *name,const char *value){
 assert(c&&value);
 if(!strcmp(name,"X-Voice-Session"))assert(!strcmp(value,session));
 if(!strcmp(name,"X-Voice-Sequence"))assert(!strcmp(value,"1"));
 if(!strcmp(name,"X-Voice-Dialogue"))assert(false);
 if(!strcmp(name,"X-Remote-Lease")){header_lease++;assert(strlen(value)==64);}
}
static int esp_http_client_open(esp_http_client_handle_t c,int size){(void)c;assert(size>=0);opens++;return tls_ok?ESP_OK:-1;}
static int esp_http_client_write(esp_http_client_handle_t c,const char *body,int size){(void)c;assert(body);writes++;return size>2?2:size;}
static int64_t esp_http_client_fetch_headers(esp_http_client_handle_t c){(void)c;return declared<0?(int)strlen(response):declared;}
static int esp_http_client_get_status_code(esp_http_client_handle_t c){(void)c;return status_code;}
static bool esp_http_client_is_chunked_response(esp_http_client_handle_t c){(void)c;return chunked;}
static int esp_http_client_read(esp_http_client_handle_t c,char *out,int size){
 (void)c;reads++;int left=(int)strlen(response)-used;if(size>left)size=left;if(size>3)size=3;
 memcpy(out,response+used,size);used+=size;if(cancel_read)alive=false;if(declared==1023)clock_us+=91000000;return size;
}
static bool esp_http_client_is_complete_data_received(esp_http_client_handle_t c){(void)c;return used==(int)strlen(response);}
static void esp_http_client_close(esp_http_client_handle_t c){(void)c;closes++;}
static void esp_http_client_cleanup(esp_http_client_handle_t c){(void)c;}
"""
code+=fn("close_http")+"\n"+fn("upload")

code+=r"""
static void reset(void){
 status_code=200;declared=-1;used=reads=opens=closes=writes=header_lease=0;clock_us=1000;
 alive=connected=tls_ok=clock_ok=true;chunked=cancel_read=false;response="{\"recognized\":true,\"recognizedText\":\"本次文字\",\"session\":\"aaaaaaaaaaaaaaaa\",\"sequence\":1}";
}
static bool request(bool stop){static uint8_t pcm[12800];return upload(pcm,stop?0:sizeof(pcm),7,session,stop);}
int main(void){
 reset();assert(request(false));assert(opens==1&&closes==1&&writes>1&&reads>1);
 reset();status_code=302;assert(!request(false));assert(opens==1&&closes==1);
 reset();tls_ok=false;assert(!request(false));assert(!writes&&!reads&&opens==1&&closes==1);
 reset();declared=1025;assert(!request(false));assert(!reads);
 reset();chunked=true;assert(!request(false));assert(!reads);
 reset();cancel_read=true;assert(!request(false));assert(reads==1);
 reset();alive=false;assert(!request(false));assert(!opens);
 assert(request(true));assert(opens==1&&closes==1&&!writes);
 reset();clock_ok=false;assert(!request(false));assert(!opens);
 reset();response="{\"recognized\":false}";assert(!request(false));
 reset();response="{\"recognized\":true,\"recognizedText\":\"other\",\"session\":\"bbbbbbbbbbbbbbbb\",\"sequence\":1}";assert(!request(false));
 reset();response="[]";assert(!request(false));
 reset();declared=100;assert(!request(false));assert(opens==1&&closes==1);
 reset();declared=1023;assert(!request(false));assert(opens==1&&closes==1);
 reset();assert(!upload(NULL,0,7,session,false));assert(!opens);
 puts("Production audio upload: raw bounded PCM/TLS/no-dialogue/no-retry/cancel/recognition/absolute deadline passed");
}

"""
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/"test.c").write_text(code)
 subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror","-fsanitize=address,undefined","-I",str(deps),"-I",str(root/"firmware-amoled/main"),str(p/"test.c"),str(deps/"cJSON.c"),"-o",str(p/"test")],check=True)
 subprocess.run([str(p/"test")],check=True)

