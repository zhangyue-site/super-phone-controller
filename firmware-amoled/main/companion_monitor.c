#include "companion_monitor.h"
#include "companion_task.h"
#include "wifi.h"
#include "identity.h"
#include "ota_ble.h"
#include "relay.h"
#include "plugin.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include "esp_timer.h"
#include <stdatomic.h>
#include <string.h>
#include <stdio.h>
static atomic_bool active,started;
static atomic_uint sync_state;
static int64_t last_attempt;
unsigned amoled_companion_monitor_state(void){return atomic_load(&sync_state);}
static unsigned epoch;
static char task_id[65];
static const char *str(const cJSON *o,const char *name){const cJSON *v=cJSON_GetObjectItemCaseSensitive(o,name);return cJSON_IsString(v)?v->valuestring:"";}
static cJSON *fetch(void){
 int64_t deadline=esp_timer_get_time()+6000000;
 char endpoint[191],url[256],body[2049];
 if(!amoled_wifi_endpoint(endpoint,sizeof(endpoint)))return NULL;
 snprintf(url,sizeof(url),"%s/board-companion",endpoint);
 esp_http_client_config_t cfg={.url=url,.timeout_ms=2000,.crt_bundle_attach=esp_crt_bundle_attach,.disable_auto_redirect=true,.buffer_size=1024,.keep_alive_enable=false};
 esp_http_client_handle_t c=esp_http_client_init(&cfg);if(!c)return NULL;
 bool ok=amoled_identity_http_auth(c)==ESP_OK;
 if(ok)esp_http_client_set_method(c,HTTP_METHOD_GET);
 if(ok)ok=esp_http_client_open(c,0)==ESP_OK;
 int used=0;
 if(ok){
  int64_t size=esp_http_client_fetch_headers(c);
  ok=size>0&&size<=2048&&esp_http_client_get_status_code(c)==200&&!esp_http_client_is_chunked_response(c);
  while(ok&&used<size){if(!atomic_load(&active)||esp_timer_get_time()>=deadline){ok=false;break;}int n=esp_http_client_read(c,body+used,(int)size-used);if(n<=0){ok=false;break;}used+=n;}
  ok=ok&&esp_http_client_is_complete_data_received(c);
 }
 esp_http_client_close(c);esp_http_client_cleanup(c);
 if(!ok||esp_timer_get_time()>=deadline)return NULL;
 body[used]=0;
 for(int i=0;i+5<used;i++)if(!memcmp(body+i,"\\u0000",6))return NULL;
 for(int i=0;i+5<used;i++)if(!memcmp(body+i,"\\u0000",6))return NULL;
 cJSON *reply=cJSON_ParseWithOpts(body,NULL,true);
 if(!cJSON_IsObject(reply)){cJSON_Delete(reply);return NULL;}return reply;
}
static void worker(void *unused){
 (void)unused;
 for(;;){
  unsigned plugin=amoled_plugin_stage();
  if(atomic_load(&active)&&!amoled_relay_direct_owned()&&!amoled_relay_audio_owned()&&plugin!=2&&plugin!=3&&plugin!=7&&plugin!=8&&amoled_wifi_connected()&&amoled_identity_ready()&&!amoled_ota_busy()){
   unsigned requested_stop=amoled_companion_stop_generation();
   atomic_store(&sync_state,1);
   cJSON *o=fetch();
   atomic_store(&sync_state,o?2:3);
   if(o){
    const char *id=str(o,"task_id");
    if(strlen(id)==32){
     if(strcmp(task_id,id)){snprintf(task_id,sizeof(task_id),"%s",id);epoch++;}
     amoled_companion_monitor_result(epoch,requested_stop,o);
    }else if(!strcmp(str(o,"state"),"idle"))amoled_companion_monitor_result(epoch,requested_stop,o);
    cJSON_Delete(o);
   }
  }
  else if(atomic_load(&active))atomic_store(&sync_state,3);
  vTaskDelay(pdMS_TO_TICKS(3000));
 }
}
void amoled_companion_monitor_enable(bool enabled){
 atomic_store(&active,enabled);
 if(!enabled)return;
 int64_t now=esp_timer_get_time();if(last_attempt&&now-last_attempt<5000000)return;
 bool expected=false;if(!atomic_compare_exchange_strong(&started,&expected,true))return;
 last_attempt=now;
 if(xTaskCreate(worker,"pet_status",6144,NULL,2,NULL)!=pdPASS)atomic_store(&started,false);
}
