/* Existing e-paper HTTPS direct protocol, fixed composite USB descriptors.
 * No USB mode switch, target capture, task creation or confirmation occurs here. */
#include "direct.h"
#include "direct_policy.h"
#include "wifi.h"
#include "relay.h"
#include "identity.h"
#include "usb.h"
#include "ota_ble.h"
#include "cJSON.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdatomic.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <math.h>
#include <time.h>
static atomic_uint generation=1;
static atomic_bool online,started,enabled;
static atomic_llong action_until;
static pc_direct policy; /* Only direct worker mutates this state. */
static char session[17];
static unsigned turn;
static uint64_t now_ms(void){return (uint64_t)esp_timer_get_time()/1000;}
void amoled_direct_cancel(void){atomic_store(&enabled,false);atomic_fetch_add(&generation,1);atomic_store(&online,false);}
bool amoled_direct_online(void){return atomic_load(&online);}
static bool live(uint32_t epoch){
 return atomic_load(&enabled)&&atomic_load(&generation)==epoch&&amoled_relay_direct_owned()&&
  amoled_wifi_connected()&&amoled_usb_armed()&&!amoled_relay_connected()&&!amoled_ota_busy()&&
  esp_timer_get_time()<atomic_load(&action_until);
}
bool amoled_direct_enable(void){
 if(!atomic_load(&started)||!amoled_identity_ready()||!amoled_wifi_connected()||
    amoled_relay_connected()||amoled_relay_direct_owned()||amoled_ota_busy()||!amoled_ota_ready())return false;
 amoled_usb_gate(true);
 if(!amoled_usb_armed())return false;
 atomic_store(&action_until,esp_timer_get_time()+20000000);
 atomic_store(&enabled,true);return true;
}
static void rotate(void){
 uint8_t bytes[8];esp_fill_random(bytes,sizeof(bytes));amoled_hex(bytes,sizeof(bytes),session);
 turn=0;pc_direct_cancel(&policy);
}
static const char *str(cJSON *o,const char *name){
 cJSON *v=cJSON_GetObjectItemCaseSensitive(o,name);return cJSON_IsString(v)?v->valuestring:"";
}
/* No request is retried. A lost ACK or partial body retires the whole turn. */
static cJSON *post(const char *path,const char *body,unsigned epoch,bool stopping){
 if((!stopping&&!live(epoch))||!amoled_wifi_connected()||time(NULL)<1700000000)return NULL;
 char endpoint[191],url[320],seq[16],response[2049];
 if(!amoled_wifi_endpoint(endpoint,sizeof(endpoint)))return NULL;
 int n=snprintf(url,sizeof(url),"%s%s",endpoint,path);if(n<0||n>=(int)sizeof(url))return NULL;
 snprintf(seq,sizeof(seq),"%u",turn);
 esp_http_client_config_t cfg={.url=url,.timeout_ms=2000,.crt_bundle_attach=esp_crt_bundle_attach,
  .disable_auto_redirect=true,.buffer_size=2048,.keep_alive_enable=false};
 esp_http_client_handle_t c=esp_http_client_init(&cfg);if(!c)return NULL;
 bool ok=amoled_identity_http_auth(c)==ESP_OK;
 esp_http_client_set_method(c,HTTP_METHOD_POST);
 esp_http_client_set_header(c,"X-Voice-Session",session);
 esp_http_client_set_header(c,"X-Voice-Sequence",seq);
 esp_http_client_set_header(c,"X-HID-Pointer","absolute-v1");
 esp_http_client_set_header(c,"X-HID-Keyboard","usb-v1");
 esp_http_client_set_header(c,"Connection","close");
 esp_http_client_set_header(c,"Content-Type","application/json");
 if(!strcmp(path,"/remote/claim")&&policy.lease[0])esp_http_client_set_header(c,"X-Remote-Lease",policy.lease);
 size_t length=body?strlen(body):0,sent=0;
 ok=ok&&esp_http_client_open(c,length)==ESP_OK;
 while(ok&&sent<length){
  if(!stopping&&!live(epoch)){ok=false;break;}
  int count=esp_http_client_write(c,body+sent,length-sent);
  if(count<=0){ok=false;break;}sent+=count;
 }
 int used=0;
 if(ok&&(stopping||live(epoch))){
  int64_t declared=esp_http_client_fetch_headers(c);
  ok=declared>=0&&declared<=2048&&esp_http_client_get_status_code(c)==200&&!esp_http_client_is_chunked_response(c);
  while(ok&&used<declared){
   if(!stopping&&!live(epoch)){ok=false;break;}
   int count=esp_http_client_read(c,response+used,(int)declared-used);
   if(count<=0){ok=false;break;}used+=count;
  }
  ok=ok&&esp_http_client_is_complete_data_received(c);
 }else ok=false;
 esp_http_client_close(c);esp_http_client_cleanup(c);
 if(!ok||(!stopping&&!live(epoch)))return NULL;
 response[used]=0;
 /* Reject JSON NUL escapes, including command text truncation. */
 for(int i=0;i+5<used;i++)if(!memcmp(response+i,"\\u0000",6))return NULL;
 cJSON *obj=cJSON_ParseWithOpts(response,NULL,true);
 if(!cJSON_IsObject(obj)){cJSON_Delete(obj);return NULL;}
 return obj;
}
static bool status_live(unsigned epoch){
 cJSON *o=post("/remote/status",NULL,epoch,false);
 bool ok=o&&!strcmp(str(o,"op"),"wait");cJSON_Delete(o);return ok&&live(epoch);
}
static bool integer(cJSON *o,const char *name,unsigned max,uint16_t *value){
 cJSON *n=cJSON_GetObjectItemCaseSensitive(o,name);
 if(!cJSON_IsNumber(n)||!isfinite(n->valuedouble)||n->valuedouble<0||
    n->valuedouble>max||floor(n->valuedouble)!=n->valuedouble)return false;
 *value=(uint16_t)n->valuedouble;return true;
}
static bool keys(cJSON *o,const char *const *names,unsigned count){
 unsigned seen=0;
 for(cJSON *v=o->child;v;v=v->next){
  unsigned i=0;for(;i<count;i++)if(v->string&&!strcmp(v->string,names[i]))break;
  if(i==count||(seen&(1u<<i)))return false;
  seen|=1u<<i;
 }
 return true;
}
static bool search_target(cJSON *o){
 cJSON *t=cJSON_GetObjectItemCaseSensitive(o,"target");uint16_t frame;
 const char *const names[]={"purpose","role","visible","focused","password","frame"};
 return cJSON_IsObject(t)&&keys(t,names,6)&&!strcmp(str(t,"purpose"),"visible_search")&&
  !strcmp(str(t,"role"),"search")&&cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(t,"visible"))&&
  cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(t,"focused"))&&
  cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(t,"password"))&&integer(t,"frame",65535,&frame)&&frame>0;
}
static bool execute(cJSON *o,unsigned epoch,const char **output){
 const char *op=str(o,"op");uint16_t args[5]={0};uint8_t command=0;
 if(!strcmp(op,"hid_home")){
  const char *const names[]={"op","id","uiRevision"};if(!keys(o,names,3))return false;
  command=1;*output="HID_HOME_REPORT_SENT";
 }else if(!strcmp(op,"hid_pointer")){
  const char *const names[]={"op","id","kind","x","y","x2","y2","duration_ms"};
  if(!keys(o,names,8)||!integer(o,"x",32767,args)||!integer(o,"y",32767,args+1))return false;
  if(!strcmp(str(o,"kind"),"click")){
   if(cJSON_HasObjectItem(o,"x2")||cJSON_HasObjectItem(o,"y2")||cJSON_HasObjectItem(o,"duration_ms"))return false;
   command=3;
  }else if(!strcmp(str(o,"kind"),"drag")){
   if(!integer(o,"x2",32767,args+2)||!integer(o,"y2",32767,args+3)||
      !integer(o,"duration_ms",1200,args+4)||args[4]<100)return false;
   command=4;
  }else return false; /* Move needs an explicit absolute-hover implementation. */
  *output="HID_POINTER_REPORT_SENT";
 }else if(!strcmp(op,"hid_key")){
  const char *const names[]={"op","id","usage","modifier","target","uiRevision"};
  if(!keys(o,names,6)||!search_target(o)||!integer(o,"usage",255,args+1))return false;
  if(cJSON_HasObjectItem(o,"modifier")&&(!integer(o,"modifier",0,args)))return false;
  if(args[1]!=0x29&&args[1]!=0x2a&&(args[1]<0x4f||args[1]>0x52))return false;
  command=13;*output="HID_KEY_REPORT_SENT";
 }else if(!strcmp(op,"hid_text")){
  const char *const names[]={"op","id","text","target","uiRevision"};
  if(!keys(o,names,5)||!search_target(o))return false;
  const char *text=str(o,"text");size_t len=strlen(text);
  if(!len||len>256)return false;
  for(size_t i=0;i<len;i++)if((unsigned char)text[i]<32||(unsigned char)text[i]>126)return false;
  for(size_t offset=0;offset<len;){
   if(!status_live(epoch))return false;
   memset(args,0,sizeof(args));size_t n=len-offset;if(n>8)n=8;args[0]=n;
   for(size_t i=0;i<n;i++)args[1+i/2]|=(uint16_t)(uint8_t)text[offset+i]<<(8*(i%2));
   if(!amoled_usb_execute(14,args,live,epoch))return false;
   offset+=n;
  }
  *output="HID_TEXT_REPORT_SENT";return live(epoch);
 }else return false;
 return status_live(epoch)&&amoled_usb_execute(command,args,live,epoch);
}
static bool result(cJSON *o,bool ok,const char *output,unsigned epoch){
 cJSON *ack=cJSON_CreateObject();if(!ack)return false;
 cJSON_AddStringToObject(ack,"id",str(o,"id"));cJSON_AddBoolToObject(ack,"ok",ok);
 cJSON_AddStringToObject(ack,"output",ok?output:"");
 if(!ok)cJSON_AddStringToObject(ack,"error","input_failed");
 char *body=cJSON_PrintUnformatted(ack);cJSON_Delete(ack);
 cJSON *reply=body?post("/dialogue/result",body,epoch,false):NULL;free(body);
 bool accepted=reply&&cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(reply,"accepted"));
 cJSON_Delete(reply);return accepted;
}
static void retire(unsigned epoch){
 atomic_store(&enabled,false);atomic_store(&online,false);amoled_usb_gate(false);
 /* STOP uses the old session/turn and may finish after local cancellation.
  * A failed STOP is never replayed and this boot nonce is retired locally. */
 cJSON *reply=post("/stop",NULL,epoch,true);cJSON_Delete(reply);
 amoled_relay_direct_release();rotate();
}
static void worker(void *unused){
 pc_direct_init(&policy);rotate();
 for(;;){
  if(!atomic_load(&enabled)||!amoled_wifi_connected()||!amoled_usb_armed()||amoled_relay_connected()||amoled_ota_busy()||!amoled_ota_ready()){
   if(amoled_relay_direct_owned())retire(atomic_load(&generation));
   vTaskDelay(pdMS_TO_TICKS(100));continue;
  }
  if(!amoled_relay_direct_acquire()){vTaskDelay(pdMS_TO_TICKS(100));continue;}
  unsigned epoch=atomic_load(&generation);
  if(turn>=2147483647){retire(epoch);continue;}turn++;
  bool had_lease=policy.lease[0]!=0;
  cJSON *claim=post("/remote/claim","{\"ready\":true}",epoch,false);
  if(!claim){retire(epoch);continue;}
  const char *lease=str(claim,"lease"),*op=str(claim,"op");
  if(lease[0]&&!pc_direct_lease(&policy,lease)){cJSON_Delete(claim);retire(epoch);continue;}
  if(!strcmp(op,"wait")){cJSON_Delete(claim);vTaskDelay(pdMS_TO_TICKS(300));continue;}
  bool begin=had_lease&&!strcmp(op,"start")&&pc_direct_begin(&policy,str(claim,"task_id"),now_ms(),
      amoled_usb_ready(),amoled_usb_armed(),amoled_relay_connected(),amoled_ota_busy());
  cJSON_Delete(claim);
  if(!begin){retire(epoch);continue;}
  atomic_store(&action_until,esp_timer_get_time()+180000000);
  atomic_store(&online,true);
  while(live(epoch)&&status_live(epoch)){
   cJSON *action=post("/dialogue/poll",NULL,epoch,false);
   if(!action)break;
   op=str(action,"op");
   if(!strcmp(op,"wait")){cJSON_Delete(action);vTaskDelay(pdMS_TO_TICKS(100));continue;}
   if(!strcmp(op,"done")||!strcmp(op,"cancelled")){cJSON_Delete(action);break;}
   bool reserved=pc_direct_reserve(&policy,str(action,"id"),now_ms(),
       amoled_usb_ready(),amoled_usb_armed(),amoled_relay_connected(),amoled_ota_busy());
   if(!reserved){cJSON_Delete(action);break;}
   const char *output="";
   bool ok=execute(action,epoch,&output);
   bool ack=result(action,ok,output,epoch);cJSON_Delete(action);
   if(!ok||!ack)break;
  }
  retire(epoch);
 }
}
esp_err_t amoled_direct_start(void){
 bool expected=false;if(!atomic_compare_exchange_strong(&started,&expected,true))return ESP_OK;
 if(xTaskCreate(worker,"amoled_direct",8192,NULL,3,NULL)!=pdPASS){atomic_store(&started,false);return ESP_ERR_NO_MEM;}
 return ESP_OK;
}
