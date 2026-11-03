/* Imported plugin metadata never selects executable code. Private server aliases
 * resolve only to the existing bounded task planner. No phone import protocol. */
#include "plugin.h"
#include "identity.h"
#include "wifi.h"
#include "relay.h"
#include "direct.h"
#include "usb.h"
#include "ota_ble.h"
#include "audio.h"
#include "cJSON.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include <stdatomic.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <time.h>
typedef struct {unsigned op,epoch,direct_epoch;char entry[97],parameters[1025];} Request;
static QueueHandle_t queue;
static atomic_bool started,busy,stop_requested;
static atomic_uint generation=1,stage;
static portMUX_TYPE text_lock=portMUX_INITIALIZER_UNLOCKED;
static char reply_text[1024],session[33],task_id[33],confirmation[33];
static int64_t pending_until;
unsigned amoled_plugin_stage(void){return atomic_load(&stage);}
bool amoled_plugin_text(char *out,size_t size){
 if(!out||size<sizeof(reply_text))return false;
 taskENTER_CRITICAL(&text_lock);memcpy(out,reply_text,sizeof(reply_text));taskEXIT_CRITICAL(&text_lock);return out[0]!=0;
}
static void message(unsigned state,const char *text){
 taskENTER_CRITICAL(&text_lock);snprintf(reply_text,sizeof(reply_text),"%s",text);atomic_store(&stage,state);taskEXIT_CRITICAL(&text_lock);
}
static bool message_current(unsigned epoch,unsigned state,const char *text){
 taskENTER_CRITICAL(&text_lock);
 bool current=atomic_load(&generation)==epoch;
 if(current){snprintf(reply_text,sizeof(reply_text),"%s",text);atomic_store(&stage,state);}
 taskEXIT_CRITICAL(&text_lock);return current;
}
static const char *str(cJSON *o,const char *name){cJSON *v=cJSON_GetObjectItemCaseSensitive(o,name);return cJSON_IsString(v)?v->valuestring:"";}
static bool hex(const char *s){
 if(strlen(s)!=32)return false;
 for(unsigned i=0;i<32;i++)if(!((s[i]>='0'&&s[i]<='9')||(s[i]>='a'&&s[i]<='f')))return false;
 return true;
}
static bool live(unsigned epoch){return atomic_load(&generation)==epoch&&amoled_wifi_connected();}
static cJSON *post(cJSON *body,unsigned epoch,bool stopping){
 if(!amoled_wifi_connected()||time(NULL)<1700000000||(!stopping&&!live(epoch)))return NULL;
 int64_t deadline=esp_timer_get_time()+(stopping?5000000:10000000);
 char endpoint[191],url[256],id[33],response[2049];uint8_t nonce[16];
 if(!amoled_wifi_endpoint(endpoint,sizeof(endpoint)))return NULL;
 esp_fill_random(nonce,sizeof(nonce));amoled_hex(nonce,sizeof(nonce),id);
 cJSON_AddStringToObject(body,"request_id",id);cJSON_AddStringToObject(body,"boot",amoled_identity_boot());
 cJSON_AddStringToObject(body,"session",session);
 char *encoded=cJSON_PrintUnformatted(body);if(!encoded)return NULL;
 size_t length=strlen(encoded),sent=0;int used=0;
 if(length>2048){free(encoded);return NULL;}
 snprintf(url,sizeof(url),"%s/board-plugin",endpoint);
 esp_http_client_config_t cfg={.url=url,.timeout_ms=3000,.crt_bundle_attach=esp_crt_bundle_attach,.disable_auto_redirect=true,.buffer_size=2048,.keep_alive_enable=false};
 esp_http_client_handle_t client=esp_http_client_init(&cfg);if(!client){free(encoded);return NULL;}
 bool ok=amoled_identity_http_auth(client)==ESP_OK;
 esp_http_client_set_method(client,HTTP_METHOD_POST);
 esp_http_client_set_header(client,"Content-Type","application/json");esp_http_client_set_header(client,"Connection","close");
 ok=ok&&esp_http_client_open(client,length)==ESP_OK;
 while(ok&&sent<length){
  if((!stopping&&!live(epoch))||esp_timer_get_time()>=deadline){ok=false;break;}
  int n=esp_http_client_write(client,encoded+sent,length-sent);if(n<=0){ok=false;break;}sent+=n;
 }
 free(encoded);
 if(ok&&(stopping||live(epoch))&&esp_timer_get_time()<deadline){
  int64_t length=esp_http_client_fetch_headers(client);int status=esp_http_client_get_status_code(client);
  ok=length>=0&&length<=2048&&(status==200||status==403||status==409)&&!esp_http_client_is_chunked_response(client);
  while(ok&&used<length){
   if((!stopping&&!live(epoch))||esp_timer_get_time()>=deadline){ok=false;break;}
   int n=esp_http_client_read(client,response+used,length-used);if(n<=0){ok=false;break;}used+=n;
  }
  ok=ok&&esp_http_client_is_complete_data_received(client);
 }else ok=false;
 esp_http_client_close(client);esp_http_client_cleanup(client);
 if(!ok||(!stopping&&!live(epoch))||esp_timer_get_time()>=deadline)return NULL;
 response[used]=0;
 for(int i=0;i+5<used;i++)if(!memcmp(response+i,"\\u0000",6))return NULL;
 cJSON *o=cJSON_ParseWithOpts(response,NULL,true);
 if(!cJSON_IsObject(o)){cJSON_Delete(o);return NULL;}return o;
}
static cJSON *request(unsigned op){
 cJSON *o=cJSON_CreateObject();if(!o)return NULL;
 cJSON_AddStringToObject(o,"operation",op==1?"prepare":op==2?"confirm":op==3?"status":"stop");
 if(op==2||op==3)cJSON_AddStringToObject(o,"task_id",task_id);
 if(op==2)cJSON_AddStringToObject(o,"confirmation",confirmation);
 return o;
}
static bool stop_server(unsigned epoch){
 if(!session[0])return false;
 cJSON *body=request(4),*reply=body?post(body,epoch,true):NULL;cJSON_Delete(body);bool stopped=reply&&!strcmp(str(reply,"state"),"stopped");cJSON_Delete(reply);
 confirmation[0]=0;return stopped;
}
static bool apply(cJSON *reply,unsigned epoch){
 if(!reply||!live(epoch))return false;
 const char *state=str(reply,"state"),*text=str(reply,"reply");
 unsigned value=!strcmp(state,"pending")?1:!strcmp(state,"queued")?2:!strcmp(state,"running")?3:
  !strcmp(state,"done")&&cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(reply,"verified"))?4:
  !strcmp(state,"stopped")||!strcmp(state,"cancelled")?6:5;
 if(value<=3||value==4){
  if(!hex(str(reply,"task_id"))||(task_id[0]&&strcmp(task_id,str(reply,"task_id"))))return false;
  memcpy(task_id,str(reply,"task_id"),33);
 }
 if(value==1){
  if(!hex(str(reply,"confirmation")))return false;
  memcpy(confirmation,str(reply,"confirmation"),33);pending_until=esp_timer_get_time()+120000000;
 }
 return message_current(epoch,value,*text?text:"插件响应无效，请重新预览")&&value!=5;
}
static void worker(void *unused){
 Request job;int64_t next_status=0;
 for(;;){
  if(atomic_exchange(&stop_requested,false)){atomic_store(&busy,true);unsigned epoch=atomic_load(&generation);bool stopped=stop_server(epoch);message_current(epoch,6,stopped?"插件已停止":"停止未确认，板端许可已撤销");atomic_store(&busy,false);}
  bool received=xQueueReceive(queue,&job,pdMS_TO_TICKS(100))==pdTRUE;
  if(!received){
   unsigned current=atomic_load(&stage);
   if(current==1&&esp_timer_get_time()>=pending_until){stop_server(atomic_load(&generation));message(5,"本次计划已过期，请重新预览");continue;}
   if(current!=2&&current!=3)continue;
   if(esp_timer_get_time()<next_status)continue;
   bool expected=false;if(!atomic_compare_exchange_strong(&busy,&expected,true))continue;
   job=(Request){.op=3,.epoch=atomic_load(&generation)};
  }
  if(!live(job.epoch)){atomic_store(&busy,false);continue;}
  cJSON *body=request(job.op);
  if(!body){message(5,"插件请求内存不足");atomic_store(&busy,false);continue;}
  if(job.op==1){
   uint8_t nonce[16];esp_fill_random(nonce,sizeof(nonce));amoled_hex(nonce,sizeof(nonce),session);
   task_id[0]=confirmation[0]=0;
   cJSON *params=cJSON_ParseWithOpts(job.parameters,NULL,true);
   if(!cJSON_IsObject(params)){cJSON_Delete(params);cJSON_Delete(body);message(5,"插件参数无效");atomic_store(&busy,false);continue;}
   cJSON_AddStringToObject(body,"entry",job.entry);cJSON_AddItemToObject(body,"parameters",params);
  }
  cJSON *reply=post(body,job.epoch,false);cJSON_Delete(body);
  bool accepted=apply(reply,job.epoch);cJSON_Delete(reply);
  unsigned applied=atomic_load(&stage);
  if(accepted&&((job.op==1&&applied!=1)||(job.op==2&&applied!=2))){message_current(job.epoch,5,"插件响应状态不匹配，请重新预览");accepted=false;}
  if(!live(job.epoch)){atomic_store(&stop_requested,true);}
  else if(!accepted){if(atomic_load(&stage)!=5)message_current(job.epoch,5,"插件请求未确认，请重新预览");stop_server(job.epoch);}
  else if(job.op==2&&!amoled_direct_enable_task_epoch(task_id,job.direct_epoch)&&live(job.epoch)){
   stop_server(job.epoch);message_current(job.epoch,5,"本地USB许可未开启，已取消队列，请重新预览");
  }
  next_status=esp_timer_get_time()+2000000;atomic_store(&busy,false);
 }
}
static bool init(void){
 if(atomic_load(&started))return true;
 queue=xQueueCreate(1,sizeof(Request));if(!queue)return false;
 if(xTaskCreate(worker,"amoled_plugin",8192,NULL,3,NULL)!=pdPASS){vQueueDelete(queue);queue=NULL;return false;}
 atomic_store(&started,true);return true;
}
bool amoled_plugin_prepare(const char *entry,const char *parameters){
 unsigned entered=atomic_load(&generation);
 if(!entry||!parameters||!entry[0]||strlen(entry)>96||strlen(parameters)>1024||
    !amoled_identity_ready()||!amoled_wifi_connected()||amoled_relay_connected()||
    amoled_relay_direct_owned()||amoled_relay_audio_owned()||amoled_ota_busy()||atomic_load(&stop_requested))return false;
 unsigned current=atomic_load(&stage);
 if(current==2||current==3)return false;
 bool expected=false;if(!atomic_compare_exchange_strong(&busy,&expected,true))return false;
 if(!init()){atomic_store(&busy,false);return false;}
 unsigned next=entered+1;
 if(!atomic_compare_exchange_strong(&generation,&entered,next)){atomic_store(&busy,false);return false;}
 Request job={.op=1,.epoch=next};
 memcpy(job.entry,entry,strlen(entry)+1);memcpy(job.parameters,parameters,strlen(parameters)+1);
 if(xQueueSend(queue,&job,0)!=pdTRUE){atomic_store(&busy,false);return false;}
 return message_current(job.epoch,7,"正在请求插件计划，尚未执行");
}
bool amoled_plugin_confirm(void){
 unsigned entered=atomic_load(&generation),permission_epoch=amoled_direct_epoch();
 if(atomic_load(&stage)!=1||!amoled_wifi_connected()||amoled_relay_connected()||
    amoled_relay_direct_owned()||amoled_relay_audio_owned()||amoled_ota_busy())return false;
 bool expected=false;if(!atomic_compare_exchange_strong(&busy,&expected,true))return false;
 Request job={.op=2,.epoch=entered,.direct_epoch=permission_epoch};
 if(xQueueSend(queue,&job,0)!=pdTRUE){atomic_store(&busy,false);return false;}
 return message_current(job.epoch,8,"正在确认本次计划，等待真实回执");
}
void amoled_plugin_cancel(void){
 if(!atomic_load(&started))return;
 atomic_fetch_add(&generation,1);atomic_store(&stop_requested,true);
 amoled_direct_cancel();amoled_usb_gate(false);message(6,"插件停止已请求，等待服务端确认");
}
