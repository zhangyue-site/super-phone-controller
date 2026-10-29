#include "ble_local.h"
#include "ble_local_policy.h"
#include "device_config.h"
#ifndef DISPLAY_DEVICE_ID
#define DISPLAY_DEVICE_ID "epaper-01"
#endif
#include "usb.h"
#include "voice.h"
#include "ble_ota.h"
#include "ota.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "psa/crypto.h"
#include <atomic>
#include <stdio.h>
#include <string.h>

// No HTTP client or network dependency: all actions terminate in the USB service.
static portMUX_TYPE mux=portMUX_INITIALIZER_UNLOCKED;
static uint16_t connection=0xffff;
static char nonce[33]={};
static uint8_t key[32]={};
static std::atomic<unsigned> generation(1),last_seq(0),last_op(0),result(0);
static std::atomic<int64_t> relay_until(0);
extern "C" bool controller_ble_relay_online(){return relay_until.load()>esp_timer_get_time();}
static std::atomic<bool> active(false),owns(false),busy(false);
struct Work {controller::BleLocalPacket command;unsigned epoch;};
static QueueHandle_t queue;
extern bool controller_usb_key(uint8_t code,bool (*live)(unsigned),unsigned sequence);
extern bool controller_usb_consumer(uint16_t usage,bool (*live)(unsigned),unsigned sequence);
extern bool controller_ble_hid_arm(bool (*live)(unsigned),unsigned epoch);
extern void controller_ble_hid_stop(void);
static bool mac(const uint8_t *secret,size_t secret_size,const void *data,size_t n,uint8_t out[32]){
 psa_key_attributes_t a=PSA_KEY_ATTRIBUTES_INIT;psa_key_id_t id=0;size_t size=0;
 psa_set_key_type(&a,PSA_KEY_TYPE_HMAC);psa_set_key_usage_flags(&a,PSA_KEY_USAGE_SIGN_MESSAGE);psa_set_key_algorithm(&a,PSA_ALG_HMAC(PSA_ALG_SHA_256));
 psa_status_t status=psa_import_key(&a,secret,secret_size,&id);psa_reset_key_attributes(&a);
 if(status==PSA_SUCCESS){status=psa_mac_compute(id,PSA_ALG_HMAC(PSA_ALG_SHA_256),(const uint8_t*)data,n,out,32,&size);psa_destroy_key(id);}
 return status==PSA_SUCCESS&&size==32;
}
static void hex(const uint8_t *p,size_t n,char *out){const char *h="0123456789abcdef";for(size_t i=0;i<n;++i){out[2*i]=h[p[i]>>4];out[2*i+1]=h[p[i]&15];}out[n*2]=0;}
static bool live(unsigned epoch){return active.load()&&generation.load()==epoch;}
extern "C" bool controller_ble_local_owns_input(){return owns.load();}
extern "C" bool controller_ble_local_connected(){
 taskENTER_CRITICAL(&mux);bool connected=connection!=0xffff&&active.load();taskEXIT_CRITICAL(&mux);return connected;
}
static void cancel_locked(){relay_until=0;active=false;generation.fetch_add(1);owns=false;result=5;}
extern "C" void controller_ble_local_cancel(){taskENTER_CRITICAL(&mux);cancel_locked();taskEXIT_CRITICAL(&mux);controller_ota_changed();}
extern "C" void controller_ble_local_connect(uint16_t conn){
 uint8_t random[16],derived[32]={};char text[33],message[160];esp_fill_random(random,sizeof(random));hex(random,16,text);
 int n=snprintf(message,sizeof(message),"PCBLE1\n%s\n%s",DISPLAY_DEVICE_ID,text);
 bool ok=n>0&&n<(int)sizeof(message)&&mac((const uint8_t*)DISPLAY_TOKEN,strlen(DISPLAY_TOKEN),message,n,derived);
 taskENTER_CRITICAL(&mux);active=false;generation.fetch_add(1);connection=conn;relay_until=0;memcpy(nonce,text,sizeof(nonce));memcpy(key,derived,sizeof(key));last_seq=0;last_op=0;result=ok?0:6;active=ok;taskEXIT_CRITICAL(&mux);memset(derived,0,sizeof(derived));controller_ota_changed();
}
extern "C" void controller_ble_local_disconnect(uint16_t conn){
 bool release=false;taskENTER_CRITICAL(&mux);if(connection==conn){release=owns.load();cancel_locked();connection=0xffff;memset(key,0,sizeof(key));}taskEXIT_CRITICAL(&mux);
 if(release){controller_release();controller_usb_request_mode(false);}
 controller_ota_changed();
}
static void worker(void*){
 Work work;
 for(;;){
  if(xQueueReceive(queue,&work,portMAX_DELAY)!=pdTRUE)continue;
  unsigned epoch=work.epoch;auto c=work.command;bool ok=false;unsigned state=6;
  taskENTER_CRITICAL(&mux);bool current=live(epoch);if(current)result=2;taskEXIT_CRITICAL(&mux);
  if(current){
   if(c.op==12){relay_until=esp_timer_get_time()+20000000;ok=true;state=3;}
   else if(controller_ota_busy()||ble_ota_busy()||controller_voice_transport_busy()){state=4;}
   else if(c.op==11){controller_ota_start();ok=controller_ota_busy();state=ok?3:6;}
   else if(c.op==6){owns=true;controller_ota_changed();ok=controller_ble_hid_arm(live,epoch);if(!ok)owns=false;state=ok?7:4;}
   else if(c.op==7){controller_release();controller_usb_request_mode(false);owns=false;ok=true;state=8;}
   else if(!owns||!controller_usb_hid_enabled()){state=4;}
   else if(c.op==1||c.op==2){ok=controller_usb_ai_key(c.op==1,live,epoch);state=ok?3:6;}
   else if(c.op==13){ok=controller_usb_keyboard((uint8_t)c.x,(uint8_t)c.y,live,epoch);state=ok?3:6;}
   else if(c.op==14){uint16_t words[]={c.y,c.x2,c.y2,c.ms};uint8_t text[8];for(unsigned i=0;i<8;++i)text[i]=words[i/2]>>(8*(i%2));ok=controller_usb_ascii(text,c.x,live,epoch);state=ok?3:6;}
   else if(c.op==8){ok=controller_usb_key((uint8_t)c.x,live,epoch);state=ok?3:6;}
   else if(c.op==9||c.op==10){ok=controller_usb_consumer(c.op==9?0x00E9:0x00EA,live,epoch);state=ok?3:6;}
   else {
    controller::PointerCommand pointer{c.op==3?controller::PointerKind::click:controller::PointerKind::drag,c.x,c.y,c.x2,c.y2,c.ms};
    ok=controller_usb_ai_pointer(pointer,live,epoch);state=ok?3:6;
   }
  }
  taskENTER_CRITICAL(&mux);if(generation.load()==epoch&&active)result=state;busy=false;taskEXIT_CRITICAL(&mux);controller_ota_changed();
 }
}
extern "C" int controller_ble_local_start(){queue=xQueueCreate(1,sizeof(Work));if(!queue)return -1;return xTaskCreate(worker,"ble_local",6144,nullptr,4,nullptr)==pdPASS?0:-1;}
extern "C" int controller_ble_local_write(uint16_t conn,const uint8_t *packet,size_t n){
 controller::BleLocalPacket command{};if(!controller::ble_local_parse(packet,n,command))return -1;
 uint8_t secret[32],signature[32]={};unsigned epoch;
 taskENTER_CRITICAL(&mux);bool allowed=conn==connection&&active;epoch=generation.load();memcpy(secret,key,32);taskEXIT_CRITICAL(&mux);
 bool signed_ok=allowed&&mac(secret,32,packet,16,signature);memset(secret,0,32);unsigned different=0;for(unsigned i=0;i<32;++i)different|=signature[i]^packet[16+i];if(!signed_ok||different)return -1;
 taskENTER_CRITICAL(&mux);
 allowed=connection==conn&&live(epoch)&&controller::ble_local_fresh(command.sequence,last_seq.load())&&(!busy||command.op==5);
 if(allowed){last_seq=command.sequence;last_op=command.op;result=1;if(command.op!=5)busy=true;}
 taskEXIT_CRITICAL(&mux);if(!allowed)return -1;
 if(command.op==5){controller_ble_hid_stop();return 0;}
 Work work{command,epoch};if(xQueueSend(queue,&work,0)!=pdTRUE){taskENTER_CRITICAL(&mux);busy=false;if(live(epoch))result=6;taskEXIT_CRITICAL(&mux);return -1;}return 0;
}
extern "C" int controller_ble_local_read(uint16_t conn,char *out,size_t capacity){
 uint8_t secret[32],signature[32]={};char challenge[33],proof[65],message[200];unsigned seq,op,state;bool working,hid,ready;
 taskENTER_CRITICAL(&mux);bool connected=connection==conn;memcpy(secret,key,32);memcpy(challenge,nonce,33);seq=last_seq;op=last_op;state=result;working=busy;hid=controller_usb_hid_enabled();ready=controller_usb_ready();taskEXIT_CRITICAL(&mux);
 if(!connected)return -1;
 int n=snprintf(message,sizeof(message),"PCBLE1-ACK\n%s\n%u\n%u\n%u\n%d\n%d\n%d",challenge,seq,op,state,hid,working,ready);
 bool ok=n>0&&n<(int)sizeof(message)&&mac(secret,32,message,n,signature);memset(secret,0,32);if(!ok)return -1;hex(signature,32,proof);
 n=snprintf(out,capacity,"{\"protocol\":\"local-hid-v1\",\"nonce\":\"%s\",\"seq\":%u,\"op\":%u,\"result\":%u,\"hid\":%d,\"busy\":%d,\"ready\":%d,\"proof\":\"%s\",\"hidKeyboardProtocol\":1,\"relayOnline\":%d,\"otaBusy\":%d,\"otaStage\":%d,\"otaProgress\":%d}",challenge,seq,op,state,hid,working,ready,proof,controller_ble_relay_online(),controller_ota_busy()||ble_ota_busy(),controller_ota_stage(),controller_ota_progress());
 return n>0&&n<(int)capacity?n:-1;
}
