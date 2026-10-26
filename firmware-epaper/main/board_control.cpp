#include "board_control.h"
#include "board_transport.h"
#include "device_auth.h"
#include "device_config.h"
#include "usb.h"
#include "ble_ota.h"
#include "ota.h"
#include "esp_app_format.h"
#include "esp_app_desc.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include "esp_random.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "cJSON.h"
#include <atomic>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#ifndef DISPLAY_DEVICE_ID
#define DISPLAY_DEVICE_ID "epaper-01"
#endif
extern "C" void controller_board_local_stop(void);
namespace {
struct Job {unsigned generation;uint8_t id[16];char session[33];char json[PC_RPC_REQUEST_MAX+1];bool detached;};
struct Reply {unsigned generation;uint8_t id[16];uint8_t kind;size_t size,offset;char json[PC_RPC_RESPONSE_MAX+1];};
static QueueHandle_t normal_queue,priority_queue;
static SemaphoreHandle_t reply_mutex;
static std::atomic<unsigned> generation(1);
static std::atomic<int> connection(-1);
static std::atomic<unsigned> busy(0);
static std::atomic<bool> transport_failed(false);
static std::atomic<unsigned> retirements_pending(0);
static pc_rpc_assembly assembly={}; // NimBLE host task owns assembly and nonce.
static char session[33];
static pc_rpc_retired retired={};
static uint8_t active_id[16]={};
static Reply reply={};
static void hex(const uint8_t *p,size_t n,char *out){static const char chars[]="0123456789abcdef";for(size_t i=0;i<n;++i){out[i*2]=chars[p[i]>>4];out[i*2+1]=chars[p[i]&15];}out[n*2]=0;}
static bool live(const Job& j){return pc_rpc_live(j.generation,generation.load(),connection.load()>=0,true);}
static void publish(const Job& j,int status,cJSON *body){
 if(!live(j))return;
 auto envelope=cJSON_CreateObject();if(!envelope)return;
 cJSON_AddNumberToObject(envelope,"status",status);cJSON_AddItemToObject(envelope,"body",body?cJSON_Duplicate(body,true):cJSON_CreateObject());
 char *text=cJSON_PrintUnformatted(envelope);cJSON_Delete(envelope);if(!text)return;
 size_t length=strlen(text);
 if(length>PC_RPC_RESPONSE_MAX){free(text);text=strdup("{\"status\":502,\"body\":{\"error\":\"board_response_too_large\"}}");if(!text)return;length=strlen(text);}
 if(xSemaphoreTake(reply_mutex,portMAX_DELAY)==pdTRUE){
  if(live(j)){reply.generation=j.generation;memcpy(reply.id,j.id,16);reply.kind=2;reply.offset=0;reply.size=length;memcpy(reply.json,text,length);}
  xSemaphoreGive(reply_mutex);
 }
 free(text);
}
static void error(const Job& j,int status,const char *message){auto body=cJSON_CreateObject();if(body){cJSON_AddStringToObject(body,"error",message);publish(j,status,body);cJSON_Delete(body);}}
static bool allowed(const char *op){return !strcmp(op,"prepare")||!strcmp(op,"confirm")||!strcmp(op,"status")||!strcmp(op,"stop")||!strcmp(op,"skills")||!strcmp(op,"skill")||!strcmp(op,"save")||!strcmp(op,"disconnect");}
static bool execute(Job& j){
 if(!j.detached && !live(j))return false;
 auto request=cJSON_Parse(j.json);auto operation=request?cJSON_GetObjectItemCaseSensitive(request,"operation"):nullptr;
 if(!cJSON_IsObject(request)||!cJSON_IsString(operation)||!allowed(operation->valuestring)||cJSON_HasObjectItem(request,"session")||cJSON_HasObjectItem(request,"request_id")){
  cJSON_Delete(request);error(j,400,"invalid_board_request");return false;
 }
 char id[33];uint8_t cloud_id[16];memcpy(cloud_id,j.id,16);if(j.detached)esp_fill_random(cloud_id,16);hex(cloud_id,16,id);cJSON_AddStringToObject(request,"session",j.session);cJSON_AddStringToObject(request,"request_id",id);
 char *body=cJSON_PrintUnformatted(request);cJSON_Delete(request);if(!body){error(j,503,"board_out_of_memory");return false;}
 if(strlen(body)>PC_RPC_REQUEST_MAX){free(body);error(j,413,"board_request_too_large");return false;}
 char url[256],auth[256];snprintf(url,sizeof(url),"%s/board-control",DISPLAY_ENDPOINT);snprintf(auth,sizeof(auth),"Bearer %s",DISPLAY_TOKEN);
 esp_http_client_config_t cfg={};cfg.url=url;cfg.crt_bundle_attach=esp_crt_bundle_attach;cfg.timeout_ms=7000;cfg.disable_auto_redirect=true;
 auto http=esp_http_client_init(&cfg);if(!http){free(body);error(j,503,"cloud_unavailable");return false;}
 esp_http_client_set_method(http,HTTP_METHOD_POST);esp_http_client_set_header(http,"Authorization",auth);esp_http_client_set_header(http,"Content-Type","application/json");esp_http_client_set_header(http,"Connection","close");
 // Direct board Internet only. Never route board RPC through ADB or phone NCM.
 size_t size=strlen(body);bool ok=(j.detached||live(j))&&esp_http_client_open(http,size)==ESP_OK;
 size_t sent=0;while(ok&&sent<size){if(!j.detached&&!live(j)){ok=false;break;}int n=esp_http_client_write(http,body+sent,size-sent);if(n<=0){ok=false;break;}sent+=n;}
 free(body);int status=0;char *response=(char*)malloc(7801);size_t used=0;
 if(ok && response && esp_http_client_fetch_headers(http)>=0){
  status=esp_http_client_get_status_code(http);
  for(;;){if(!j.detached&&!live(j)){ok=false;break;}char extra;int n=esp_http_client_read(http,used<7800?response+used:&extra,used<7800?7800-used:1);if(n<0){ok=false;break;}if(n==0){ok=esp_http_client_is_complete_data_received(http);break;}if(used+(size_t)n>7800){ok=false;break;}used+=n;}
 }else ok=false;
 esp_http_client_close(http);esp_http_client_cleanup(http);
 if(ok){response[used]=0;auto parsed=cJSON_Parse(response);if(cJSON_IsObject(parsed))publish(j,status,parsed);else error(j,502,"invalid_cloud_response");cJSON_Delete(parsed);}else error(j,503,"cloud_unavailable_or_cancelled");
 free(response);
 return ok && (status==200 || status==403);
}
static void worker(void *arg){QueueHandle_t queue=arg?priority_queue:normal_queue;Job job;for(;;){if(xQueueReceive(queue,&job,portMAX_DELAY)!=pdTRUE)continue;bool delivered=execute(job);if(job.detached){if(!delivered)transport_failed=true;retirements_pending.fetch_sub(1);}unsigned captured=job.generation;busy.compare_exchange_strong(captured,0);}}
static Job make_job(const uint8_t *id){Job j={};j.generation=generation.load();memcpy(j.id,id,16);memcpy(j.session,session,33);return j;}
}
bool controller_board_control_busy(){return busy.load();}
bool controller_board_control_start(){
 reply_mutex=xSemaphoreCreateMutex();normal_queue=xQueueCreate(1,sizeof(Job));priority_queue=xQueueCreate(8,sizeof(Job));
 if(!reply_mutex||!normal_queue||!priority_queue)return false;
 return xTaskCreate(worker,"board_rpc",8192,nullptr,3,nullptr)==pdPASS && xTaskCreate(worker,"board_stop",8192,(void*)1,6,nullptr)==pdPASS;
}
void controller_board_control_connect(uint16_t conn){generation.fetch_add(1);connection=conn;busy=false;memset(&retired,0,sizeof(retired));memset(active_id,0,16);memset(&assembly,0,sizeof(assembly));uint8_t nonce[16];esp_fill_random(nonce,16);hex(nonce,16,session);}
void controller_board_control_disconnect(){
 if(connection.load()<0)return;
 uint8_t id[16];esp_fill_random(id,16);Job j=make_job(id);strcpy(j.json,"{\"operation\":\"disconnect\"}");j.detached=true;
 retirements_pending.fetch_add(1);connection=-1;generation.fetch_add(1);busy=false;memset(&assembly,0,sizeof(assembly));controller_board_local_stop();
 if(xQueueSend(priority_queue,&j,0)!=pdTRUE)transport_failed=true;
}
int controller_board_control_write(uint16_t conn,const uint8_t *packet,size_t length){
 if(connection.load()!=conn || length<PC_RPC_HEADER || packet[0]!=1)return -1;
 if(packet[1]==3){
  if(length!=PC_RPC_HEADER || packet[18]||packet[19]||packet[20]||packet[21])return -1;
  bool fenced=pc_rpc_retire(&retired,packet+2);
  if(assembly.used)fenced=pc_rpc_retire(&retired,assembly.id)&&fenced;
  const uint8_t empty_id[16]={};
  if(memcmp(active_id,empty_id,16))fenced=pc_rpc_retire(&retired,active_id)&&fenced;
  memset(active_id,0,16);
  generation.fetch_add(1);memset(&assembly,0,sizeof(assembly));controller_board_local_stop();busy=generation.load();
  // Retire the old cloud nonce before permitting any new request. An in-flight
  // HTTP confirm keeps that nonce and is rejected if it arrives after retirement.
  Job j=make_job(packet+2);strcpy(j.json,"{\"operation\":\"disconnect\"}");j.detached=true;
  uint8_t nonce[16];esp_fill_random(nonce,16);hex(nonce,16,session);
  retirements_pending.fetch_add(1);
  if(!fenced)transport_failed=true;
  if(xQueueSendToFront(priority_queue,&j,0)==pdTRUE)return 0;
  transport_failed=true;return -1;
 }
 if(pc_rpc_is_retired(&retired,packet+2))return -1;
 if(transport_failed || retirements_pending || busy || ble_ota_busy() || controller_ota_busy())return -1;
 int complete=pc_rpc_push_guarded(&assembly,&retired,packet,length);if(complete<0)return -1;
 if(complete){
  Job j=make_job(assembly.id);memcpy(active_id,assembly.id,16);memcpy(j.json,assembly.data,assembly.total+1);bool invalid=memchr(j.json,0,assembly.total)!=nullptr;
  memset(&assembly,0,sizeof(assembly));if(invalid)return -1;busy=generation.load();
  if(xQueueSend(normal_queue,&j,0)!=pdTRUE){busy=false;return -1;}
 }
 return 0;
}
int controller_board_control_read(uint16_t conn,uint8_t *out,size_t capacity){
 if(connection.load()!=conn || capacity<=PC_RPC_HEADER || xSemaphoreTake(reply_mutex,0)!=pdTRUE)return -1;
 if(reply.generation!=generation.load()){
  if(busy){xSemaphoreGive(reply_mutex);return -1;}
  memset(&reply,0,sizeof(reply));reply.generation=generation.load();reply.kind=4;
  reply.size=snprintf(reply.json,sizeof(reply.json),"{\"protocol\":1,\"session\":\"%s\",\"device\":\"%s\"}",session,DISPLAY_DEVICE_ID);
 }
 if(reply.offset>=reply.size){xSemaphoreGive(reply_mutex);return -1;}
 size_t length=reply.size-reply.offset;if(length>capacity-PC_RPC_HEADER)length=capacity-PC_RPC_HEADER;
 out[0]=1;out[1]=reply.kind;memcpy(out+2,reply.id,16);out[18]=reply.offset&255;out[19]=reply.offset>>8;out[20]=reply.size&255;out[21]=reply.size>>8;memcpy(out+PC_RPC_HEADER,reply.json+reply.offset,length);reply.offset+=length;
 xSemaphoreGive(reply_mutex);return PC_RPC_HEADER+length;
}
bool controller_board_usb_command(const char *line){
 if(strncmp(line,"PCUSB ",6))return false;
 char id[33];uint8_t nonce[32],proof[32];int op=pc_usb_parse(line,id,nonce);if(!op)return true;
 auto object=cJSON_CreateObject();if(!object)return true;
 cJSON_AddStringToObject(object,"device",DISPLAY_DEVICE_ID);cJSON_AddStringToObject(object,"usbSerial",controller_usb_serial());
 if(op==1){cJSON_AddNumberToObject(object,"protocol",1);cJSON_AddStringToObject(object,"version",esp_app_get_description()->version);}
 else {char domain[192];int domain_length=pc_usb_domain(DISPLAY_DEVICE_ID,controller_usb_serial(),domain,sizeof(domain));if(domain_length>0 && controller_device_sign(domain,nonce,proof)){char encoded[65];hex(proof,32,encoded);cJSON_AddStringToObject(object,"proof",encoded);}else cJSON_AddStringToObject(object,"error","signing_failed");memset(proof,0,sizeof(proof));memset(nonce,0,sizeof(nonce));}
 char *json=cJSON_PrintUnformatted(object);cJSON_Delete(object);if(json){char output[512];int n=snprintf(output,sizeof(output),"PCUSB %s %s\r\n",id,json);free(json);if(n>0 && n<(int)sizeof(output))controller_usb_write(output);}return true;
}
