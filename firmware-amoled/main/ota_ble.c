#include "ota_ble.h"
#include "ota_engine.h"
#include "version_policy.h"
#include "identity.h"
#include "usb.h"
#include "esp_app_desc.h"
#include "esp_app_format.h"
#include "esp_ota_ops.h"
#include "esp_timer.h"
#include "esp_random.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "host/ble_hs.h"
#include "psa/crypto.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
static pc_ota engine;
static QueueHandle_t queue;
static portMUX_TYPE lock=portMUX_INITIALIZER_UNLOCKED;
static uint16_t connection=BLE_HS_CONN_HANDLE_NONE;
uint16_t amoled_ota_status_handle;
static uint8_t challenge[32],grant_digest[32];
static uint32_t grant_size;static char grant_version[32];
static bool challenge_live;static uint64_t challenge_issued;
static atomic_bool pending,ready;
static atomic_ullong wifi_deadline;
static esp_ota_handle_t handle;
static const esp_partition_t *partition;
static psa_hash_operation_t sha=PSA_HASH_OPERATION_INIT;
static bool sha_live;
static uint8_t expected_digest[32];static uint32_t expected_size;static char expected_version[32];
typedef struct {unsigned epoch;uint16_t length;uint8_t bytes[512];} Chunk;
static uint64_t now_ms(void){return esp_timer_get_time()/1000;}
static bool authorized_release_version(const char *target,const char *current){
 return amoled_release_version_valid(target)&&amoled_release_version_valid(current);
}
static bool begin_image(void *ctx,uint32_t total){
 amoled_usb_gate(false);
 taskENTER_CRITICAL(&lock);memcpy(expected_digest,grant_digest,32);expected_size=grant_size;memcpy(expected_version,grant_version,32);taskEXIT_CRITICAL(&lock);
 if(total!=expected_size||memcmp(expected_digest,engine.digest,32)||!authorized_release_version(expected_version,esp_app_get_description()->version))return false;
 partition=esp_ota_get_next_update_partition(NULL);
 if(!partition||partition==esp_ota_get_running_partition()||total>partition->size)return false;
 if(esp_ota_begin(partition,OTA_WITH_SEQUENTIAL_WRITES,&handle)!=ESP_OK){handle=0;return false;}
 sha=(psa_hash_operation_t)PSA_HASH_OPERATION_INIT;
 sha_live=psa_hash_setup(&sha,PSA_ALG_SHA_256)==PSA_SUCCESS;return sha_live;
}
static bool write_image(void *ctx,const uint8_t *bytes,size_t length){return handle&&esp_ota_write(handle,bytes,length)==ESP_OK&&psa_hash_update(&sha,bytes,length)==PSA_SUCCESS;}
static void abort_image(void *ctx){if(handle){esp_ota_abort(handle);handle=0;}if(sha_live){psa_hash_abort(&sha);sha_live=false;}}
static bool verify_image(void *ctx,const uint8_t digest[32]){
 uint8_t actual[32];size_t n=0;bool ok=sha_live&&psa_hash_finish(&sha,actual,32,&n)==PSA_SUCCESS&&n==32;sha_live=false;
 if(!ok||memcmp(actual,digest,32)||memcmp(actual,expected_digest,32))return false;
 esp_err_t e=esp_ota_end(handle);handle=0;if(e!=ESP_OK)return false;
 esp_app_desc_t desc={0};return esp_ota_get_partition_description(partition,&desc)==ESP_OK&&
  !strcmp(desc.project_name,"phone_controller_amoled")&&!strcmp(desc.version,expected_version)&&authorized_release_version(desc.version,esp_app_get_description()->version);
}
static bool commit_allowed(void *ctx){uint64_t deadline=atomic_load(&wifi_deadline);return !deadline||now_ms()<deadline;}
static bool commit_image(void *ctx){return esp_ota_set_boot_partition(partition)==ESP_OK;}
void amoled_ota_status(uint8_t out[4]){out[0]=pc_ota_state(&engine);out[1]=atomic_load(&engine.progress);out[2]=atomic_load(&engine.error);out[3]=0;}
static void notify(void){
 uint16_t conn;taskENTER_CRITICAL(&lock);conn=connection;taskEXIT_CRITICAL(&lock);
 if(conn==BLE_HS_CONN_HANDLE_NONE||!amoled_ota_status_handle)return;
 uint8_t out[4];amoled_ota_status(out);struct os_mbuf *om=ble_hs_mbuf_from_flat(out,4);if(om)ble_gatts_notify_custom(conn,amoled_ota_status_handle,om);
}
static void restart_image(void *ctx){notify();vTaskDelay(pdMS_TO_TICKS(1200));esp_restart();}
bool amoled_ota_busy(void){return atomic_load(&pending)||atomic_load(&engine.power_requested)||pc_ota_busy(&engine);}
bool amoled_ota_ready(void){return atomic_load(&ready);}
void amoled_ota_cancel(void){if(!atomic_load(&ready))return;taskENTER_CRITICAL(&lock);challenge_live=false;memset(challenge,0,32);pc_ota_cancel(&engine);taskEXIT_CRITICAL(&lock);amoled_usb_gate(false);}
void amoled_ota_connect(uint16_t conn){amoled_ota_cancel();atomic_store(&wifi_deadline,0);taskENTER_CRITICAL(&lock);connection=conn;challenge_live=false;memset(challenge,0,32);taskEXIT_CRITICAL(&lock);}
void amoled_ota_disconnect(void){amoled_ota_cancel();taskENTER_CRITICAL(&lock);connection=BLE_HS_CONN_HANDLE_NONE;challenge_live=false;memset(challenge,0,32);taskEXIT_CRITICAL(&lock);}
static void writer(void *arg){
 Chunk *c=malloc(sizeof(*c));if(!c){atomic_store(&ready,false);vTaskDelete(NULL);return;}
 uint8_t before[4]={0},after[4];for(;;){
  if(xQueueReceive(queue,c,pdMS_TO_TICKS(100))==pdTRUE){
   pc_ota_process(&engine,c->epoch,c->bytes,c->length,now_ms());
   if(!pc_ota_busy(&engine))atomic_store(&pending,false);
  }
  bool was_busy=pc_ota_busy(&engine);pc_ota_tick(&engine,now_ms());
  if(was_busy&&!pc_ota_busy(&engine))atomic_store(&pending,false);
  amoled_ota_status(after);if(memcmp(before,after,4)){notify();memcpy(before,after,4);}
 }
}
esp_err_t amoled_ota_init(void){
 pc_ota_hooks h={begin_image,write_image,verify_image,commit_image,abort_image,restart_image,commit_allowed};pc_ota_init(&engine,h,NULL);
 queue=xQueueCreate(8,sizeof(Chunk));if(!queue)return ESP_ERR_NO_MEM;
 if(xTaskCreate(writer,"amoled_ota",6144,NULL,4,NULL)!=pdPASS){vQueueDelete(queue);queue=NULL;return ESP_ERR_NO_MEM;}
 atomic_store(&ready,true);return ESP_OK;
}
static bool reserve_input(void){bool expected=false;return !atomic_load(&engine.power_requested)&&!pc_ota_busy(&engine)&&atomic_compare_exchange_strong(&pending,&expected,true);}
int amoled_ota_access(uint16_t conn,uint16_t attr,struct ble_gatt_access_ctxt *ctxt,void *arg){
 if(!amoled_ota_ready())return BLE_ATT_ERR_UNLIKELY;
 taskENTER_CRITICAL(&lock);bool current=connection==conn;taskEXIT_CRITICAL(&lock);if(!current)return BLE_ATT_ERR_INSUFFICIENT_AUTHEN;
 unsigned auth_epoch=pc_ota_epoch(&engine);
 uintptr_t kind=(uintptr_t)arg;
 if(kind==3&&ctxt->op==BLE_GATT_ACCESS_OP_READ_CHR){uint8_t out[4];amoled_ota_status(out);return os_mbuf_append(ctxt->om,out,4)?BLE_ATT_ERR_INSUFFICIENT_RES:0;}
 if(kind==9){
  if(amoled_ota_busy())return BLE_ATT_ERR_UNLIKELY;
  if(ctxt->op==BLE_GATT_ACCESS_OP_READ_CHR){
   atomic_store(&engine.grant_until,0);uint8_t next[32];esp_fill_random(next,32);
   taskENTER_CRITICAL(&lock);bool current_epoch=connection==conn&&pc_ota_epoch(&engine)==auth_epoch;
   if(current_epoch){memcpy(challenge,next,32);challenge_issued=now_ms();challenge_live=true;}taskEXIT_CRITICAL(&lock);
   if(!current_epoch)return BLE_ATT_ERR_INSUFFICIENT_AUTHEN;
   return os_mbuf_append(ctxt->om,next,32)?BLE_ATT_ERR_INSUFFICIENT_RES:0;
  }
  if(ctxt->op!=BLE_GATT_ACCESS_OP_WRITE_CHR||OS_MBUF_PKTLEN(ctxt->om)!=100)return BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN;
  uint8_t raw[100],nonce[32],expected[32]={0},message[320];uint16_t length;
  if(ble_hs_mbuf_to_flat(ctxt->om,raw,100,&length))return BLE_ATT_ERR_UNLIKELY;
  taskENTER_CRITICAL(&lock);uint64_t issued=challenge_issued;bool valid=challenge_live&&pc_ota_challenge_valid(issued,now_ms());challenge_live=false;memcpy(nonce,challenge,32);memset(challenge,0,32);taskEXIT_CRITICAL(&lock);
  atomic_store(&engine.grant_until,0);if(!valid||!memchr(raw,0,32))return BLE_ATT_ERR_INSUFFICIENT_AUTHEN;
  size_t vn=strnlen((char*)raw,32);for(size_t i=vn;i<32;i++)if(raw[i])return BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN;
  if(!authorized_release_version((char*)raw,esp_app_get_description()->version))return BLE_ATT_ERR_VALUE_NOT_ALLOWED;
  int n=snprintf((char*)message,sizeof(message),"PCOTA-AUTH2\n%s\n%s\nphone_controller_amoled\n%s\n",amoled_identity_device(),amoled_identity_boot(),(char*)raw);
  if(n<0||(size_t)n+68>sizeof(message))return BLE_ATT_ERR_UNLIKELY;
  memcpy(message+n,nonce,32);memcpy(message+n+32,raw+32,36);
  bool ok=amoled_identity_hmac(message,n+68,expected);unsigned diff=0;for(unsigned i=0;i<32;i++)diff|=raw[68+i]^expected[i];memset(expected,0,32);memset(message,0,sizeof(message));
  uint32_t size=(uint32_t)raw[64]|((uint32_t)raw[65]<<8)|((uint32_t)raw[66]<<16)|((uint32_t)raw[67]<<24);
  if(!ok||diff||size<4096||size>0x600000)return BLE_ATT_ERR_INSUFFICIENT_AUTHEN;
  taskENTER_CRITICAL(&lock);valid=connection==conn&&pc_ota_epoch(&engine)==auth_epoch&&pc_ota_challenge_valid(issued,now_ms());
  if(valid){memcpy(grant_version,raw,32);memcpy(grant_digest,raw+32,32);grant_size=size;pc_ota_grant(&engine,issued);}
  taskEXIT_CRITICAL(&lock);return valid?0:BLE_ATT_ERR_INSUFFICIENT_AUTHEN;
 }
 if(kind!=2||ctxt->op!=BLE_GATT_ACCESS_OP_WRITE_CHR)return BLE_ATT_ERR_UNLIKELY;
 Chunk c={0};c.epoch=pc_ota_epoch(&engine);c.length=OS_MBUF_PKTLEN(ctxt->om);
 if(c.length<1||c.length>512||ble_hs_mbuf_to_flat(ctxt->om,c.bytes,c.length,NULL))return BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN;
 unsigned cmd=c.bytes[0];
 if(cmd==4&&c.length==1){amoled_ota_cancel();return 0;}
 if(cmd<1||cmd>3||(cmd==1&&c.length!=37)||(cmd==2&&c.length<2)||(cmd==3&&c.length!=1))return BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN;
 if(cmd==1){
  if(atomic_load(&engine.grant_until)<=now_ms()||!amoled_usb_reserve_ota(reserve_input))return BLE_ATT_ERR_INSUFFICIENT_AUTHEN;
 }else if(!amoled_ota_busy())return BLE_ATT_ERR_INSUFFICIENT_AUTHEN;
 if(xQueueSend(queue,&c,0)!=pdTRUE){if(cmd==1)atomic_store(&pending,false);return BLE_ATT_ERR_INSUFFICIENT_RES;}
 return 0;
}

bool amoled_ota_wifi_live(unsigned epoch){
 return amoled_ota_ready()&&!atomic_load(&engine.power_requested)&&pc_ota_epoch(&engine)==epoch&&amoled_ota_busy();
}
bool amoled_ota_wifi_begin(const char *version,uint32_t size,const uint8_t digest[32],uint64_t deadline,unsigned *epoch){
 if(deadline<=now_ms()||!version||strlen(version)>=32||!digest||!epoch||size<4096||size>0x600000||
    !amoled_ota_ready()||!authorized_release_version(version,esp_app_get_description()->version))return false;
 taskENTER_CRITICAL(&lock);
 bool idle=connection==BLE_HS_CONN_HANDLE_NONE&&!amoled_ota_busy();
 unsigned before=pc_ota_epoch(&engine);
 taskEXIT_CRITICAL(&lock);
 if(!idle||!amoled_usb_reserve_ota(reserve_input))return false;
 Chunk c={0};c.epoch=before;c.length=37;c.bytes[0]=1;
 c.bytes[1]=size;c.bytes[2]=size>>8;c.bytes[3]=size>>16;c.bytes[4]=size>>24;
 memcpy(c.bytes+5,digest,32);
 taskENTER_CRITICAL(&lock);
 bool valid=connection==BLE_HS_CONN_HANDLE_NONE&&pc_ota_epoch(&engine)==before;
 if(valid){
  memset(grant_version,0,sizeof(grant_version));memcpy(grant_version,version,strlen(version));
  atomic_store(&wifi_deadline,deadline);
  memcpy(grant_digest,digest,32);grant_size=size;pc_ota_grant(&engine,now_ms());
 }
 taskEXIT_CRITICAL(&lock);
 if(!valid||xQueueSend(queue,&c,0)!=pdTRUE){atomic_store(&pending,false);return false;}
 *epoch=before;return true;
}
bool amoled_ota_wifi_chunk(unsigned epoch,const uint8_t *bytes,size_t length,bool final){
 if(!amoled_ota_wifi_live(epoch)||length>511||(!final&&(!bytes||!length))||(final&&length))return false;
 Chunk c={0};c.epoch=epoch;c.length=final?1:length+1;c.bytes[0]=final?3:2;
 if(length)memcpy(c.bytes+1,bytes,length);
 return xQueueSend(queue,&c,pdMS_TO_TICKS(100))==pdTRUE;
}

bool amoled_ota_prepare_power(void){return !amoled_ota_ready()||pc_ota_request_power(&engine);}
bool amoled_ota_power_idle(void){return !amoled_ota_ready()||(pc_ota_power_ready(&engine)&&!atomic_load(&pending));}
void amoled_ota_finish_power(void){if(amoled_ota_ready())pc_ota_release_power(&engine);}
