"""Production direct HTTPS adapter: fake transport, real cJSON, no device/API use."""
from pathlib import Path
import argparse,subprocess,tempfile
root=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument("--cjson-dir",required=True);args=ap.parse_args();deps=Path(args.cjson_dir)
source=(root/"firmware-amoled/main/direct.c").read_text()
def fn(name):
 start=source.index(name+"(");start=source.rfind("\n",0,start)+1
 brace=source.index("{",start);end=brace+1;depth=1
 while depth:
  depth+=(source[end]=="{")-(source[end]=="}");end+=1
 return source[start:end]
code=r"""
#include "cJSON.h"
#include "direct_policy.h"
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
static pc_direct policy;static char session[17]="aaaaaaaaaaaaaaaa";static unsigned turn=8;
static int status_code=200,declared=-1,used,reads,opens,closes,writes,header_lease;
static bool alive=true,connected=true,tls_ok=true,chunked,cancel_read,clock_ok=true;
static const char *response="{\"op\":\"wait\"}";
static int bundle;
#define esp_crt_bundle_attach (&bundle)
static bool live(uint32_t epoch){return epoch==7&&alive;}
static bool amoled_wifi_connected(void){return connected;}
static bool amoled_wifi_endpoint(char *out,size_t capacity){assert(capacity>=191);strcpy(out,"https://controller.test");return true;}
static time_t fake_time(time_t *out){(void)out;return clock_ok?1800000000:0;}
#define time fake_time
static esp_http_client_handle_t esp_http_client_init(const esp_http_client_config_t *cfg){
 assert(cfg->disable_auto_redirect&&cfg->crt_bundle_attach==&bundle&&cfg->timeout_ms==2000);
 assert(!strncmp(cfg->url,"https://controller.test/",strlen("https://controller.test/")));return &bundle;
}
static int amoled_identity_http_auth(esp_http_client_handle_t c){assert(c);return ESP_OK;}
#define HTTP_METHOD_POST 1
static void esp_http_client_set_method(esp_http_client_handle_t c,int method){assert(c&&method==1);}
static void esp_http_client_set_header(esp_http_client_handle_t c,const char *name,const char *value){
 assert(c&&value);
 if(!strcmp(name,"X-Voice-Session"))assert(!strcmp(value,session));
 if(!strcmp(name,"X-Voice-Sequence"))assert(!strcmp(value,"8"));
 if(!strcmp(name,"X-Remote-Lease")){header_lease++;assert(strlen(value)==64);}
}
static int esp_http_client_open(esp_http_client_handle_t c,int size){(void)c;assert(size>=0);opens++;return tls_ok?ESP_OK:-1;}
static int esp_http_client_write(esp_http_client_handle_t c,const char *body,int size){(void)c;assert(body);writes++;return size>2?2:size;}
static int64_t esp_http_client_fetch_headers(esp_http_client_handle_t c){(void)c;return declared<0?(int)strlen(response):declared;}
static int esp_http_client_get_status_code(esp_http_client_handle_t c){(void)c;return status_code;}
static bool esp_http_client_is_chunked_response(esp_http_client_handle_t c){(void)c;return chunked;}
static int esp_http_client_read(esp_http_client_handle_t c,char *out,int size){
 (void)c;reads++;int left=(int)strlen(response)-used;if(size>left)size=left;if(size>3)size=3;
 memcpy(out,response+used,size);used+=size;if(cancel_read)alive=false;return size;
}
static bool esp_http_client_is_complete_data_received(esp_http_client_handle_t c){(void)c;return used==(int)strlen(response);}
static void esp_http_client_close(esp_http_client_handle_t c){(void)c;closes++;}
static void esp_http_client_cleanup(esp_http_client_handle_t c){(void)c;}
"""
code+=fn("post")
code+=r"""
static void reset(void){
 pc_direct_init(&policy);memset(policy.lease,'b',64);policy.lease[64]=0;
 status_code=200;declared=-1;used=reads=opens=closes=writes=header_lease=0;
 alive=connected=tls_ok=clock_ok=true;chunked=cancel_read=false;response="{\"op\":\"wait\"}";
}
static bool request(const char *path,bool stopping){cJSON *o=post(path,"{\"ready\":true}",7,stopping);bool ok=o;cJSON_Delete(o);return ok;}
int main(void){
 reset();assert(request("/remote/claim",false));assert(opens==1&&closes==1&&header_lease==1&&writes>1&&reads>1);
 reset();status_code=302;assert(!request("/remote/claim",false));assert(opens==1&&closes==1);
 reset();tls_ok=false;assert(!request("/remote/claim",false));assert(!writes&&!reads&&opens==1&&closes==1);
 reset();declared=2049;assert(!request("/dialogue/poll",false));assert(!reads);
 reset();chunked=true;assert(!request("/dialogue/poll",false));assert(!reads);
 reset();cancel_read=true;assert(!request("/dialogue/poll",false));assert(reads==1);
 reset();alive=false;assert(!request("/dialogue/poll",false));assert(!opens);
 assert(request("/stop",true));assert(opens==1&&closes==1); /* Retire old session after local STOP. */
 reset();clock_ok=false;assert(!request("/remote/claim",false));assert(!opens);
 reset();response="{\"op\":\"hid_text\",\"text\":\"a\\u0000b\"}";assert(!request("/dialogue/poll",false));
 reset();response="[]";assert(!request("/dialogue/poll",false));
 reset();declared=100;assert(!request("/dialogue/poll",false));assert(opens==1&&closes==1);
 puts("Production direct HTTPS: TLS/redirect/body limits/lease/partial writes/late STOP/NUL/no-retry passed");
}
"""
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/"test.c").write_text(code)
 subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror","-fsanitize=address,undefined","-I",str(deps),"-I",str(root/"firmware-amoled/main"),str(p/"test.c"),str(deps/"cJSON.c"),str(root/"firmware-amoled/main/direct_policy.c"),"-o",str(p/"test")],check=True)
 subprocess.run([str(p/"test")],check=True)

