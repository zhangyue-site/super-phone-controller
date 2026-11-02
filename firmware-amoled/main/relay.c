#include "relay.h"
#include "identity.h"
#include "usb.h"
#include "ota_ble.h"
#include "wifi.h"
#include "esp_ota_ops.h"
#include <stdio.h>
#include <string.h>
#include <stdatomic.h>
#include "esp_app_desc.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "host/ble_hs.h"
#include "host/util/util.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"
#define UUID(n) BLE_UUID128_INIT(n,0,0,0,0,0,0,0,0x61,0x74,0x6f,0x2d,0x61,0x74,0x6f,0x6f)
static const ble_uuid128_t service_uuid=UUID(1),ctrl_uuid=UUID(2),stat_uuid=UUID(3),info_uuid=UUID(4),auth_uuid=UUID(5),local_uuid=UUID(8),upgrade_uuid=UUID(9);
static portMUX_TYPE mux=portMUX_INITIALIZER_UNLOCKED;
static uint16_t connection=BLE_HS_CONN_HANDLE_NONE;
static uint8_t addr_type,key[32],auth_proof[32];
static char nonce[33];
static bool auth_ready,active,started,busy;
static atomic_bool synced;
bool amoled_relay_ready(void){return started&&atomic_load(&synced)&&amoled_ota_ready();}
static atomic_uint epoch=1;
static unsigned sequence,operation,result;
static atomic_llong relay_until;
static QueueHandle_t queue;
typedef struct {uint8_t op;uint32_t sequence,epoch;uint16_t a[5];} Work;
static bool live(uint32_t e){return atomic_load(&epoch)==e&&amoled_relay_connected();}
bool amoled_relay_connected(void){taskENTER_CRITICAL(&mux);bool v=active&&connection!=BLE_HS_CONN_HANDLE_NONE;taskEXIT_CRITICAL(&mux);return v;}
bool amoled_relay_online(void){return amoled_relay_connected()&&atomic_load(&relay_until)>esp_timer_get_time();}
void amoled_relay_cancel(void){amoled_wifi_cancel();taskENTER_CRITICAL(&mux);atomic_fetch_add(&epoch,1);relay_until=0;result=5;taskEXIT_CRITICAL(&mux);amoled_usb_gate(false);amoled_ota_cancel();}
void amoled_relay_usb_detached(void){amoled_relay_cancel();}
static bool parse(const uint8_t p[48],Work *w){
 if(p[0]!=1||p[1]<1||p[1]>14)return false;
 w->op=p[1];w->sequence=(uint32_t)p[2]|((uint32_t)p[3]<<8)|((uint32_t)p[4]<<16)|((uint32_t)p[5]<<24);if(!w->sequence)return false;
 for(int i=0;i<5;i++)w->a[i]=p[6+2*i]|(p[7+2*i]<<8);
 uint16_t *a=w->a;
 if(w->op==3)return a[0]<=32767&&a[1]<=32767&&!a[2]&&!a[3]&&!a[4];
 if(w->op==4)return a[0]<=32767&&a[1]<=32767&&a[2]<=32767&&a[3]<=32767&&a[4]>=100&&a[4]<=1200;
 if(w->op==8)return a[0]>=4&&a[0]<=231&&!a[1]&&!a[2]&&!a[3]&&!a[4];
 if(w->op==13)return a[0]<=255&&((a[1]>=4&&a[1]<=0x2c)||(a[1]>=0x4f&&a[1]<=0x52))&&!a[2]&&!a[3]&&!a[4];
 if(w->op==14){if(a[0]<1||a[0]>8)return false;for(int i=0;i<8;i++){uint8_t c=a[1+i/2]>>(8*(i%2));if(i<a[0]?(c<32||c>126):c!=0)return false;}return true;}
 return !a[0]&&!a[1]&&!a[2]&&!a[3]&&!a[4];
}
static int command(uint16_t conn,const uint8_t p[48]){
 Work w={0};if(!parse(p,&w))return BLE_ATT_ERR_VALUE_NOT_ALLOWED;
 if(amoled_ota_busy()&&w.op!=5&&w.op!=7)return BLE_ATT_ERR_UNLIKELY;
 uint8_t snapshot[32],proof[32];taskENTER_CRITICAL(&mux);bool allowed=active&&connection==conn;w.epoch=epoch;memcpy(snapshot,key,32);taskEXIT_CRITICAL(&mux);
 bool signed_ok=allowed&&amoled_hmac(snapshot,32,p,16,proof);memset(snapshot,0,32);unsigned diff=0;if(signed_ok)for(int i=0;i<32;i++)diff|=proof[i]^p[16+i];memset(proof,0,32);if(!signed_ok||diff)return BLE_ATT_ERR_INSUFFICIENT_AUTHEN;
 taskENTER_CRITICAL(&mux);allowed=active&&connection==conn&&epoch==w.epoch&&w.sequence>sequence&&(!busy||w.op==5);
 if(allowed){sequence=w.sequence;operation=w.op;result=1;if(w.op!=5)busy=true;}taskEXIT_CRITICAL(&mux);
 if(!allowed)return BLE_ATT_ERR_UNLIKELY;
 if(w.op==5){amoled_relay_cancel();return 0;}
 if(xQueueSend(queue,&w,0)!=pdTRUE){taskENTER_CRITICAL(&mux);busy=false;result=6;taskEXIT_CRITICAL(&mux);return BLE_ATT_ERR_INSUFFICIENT_RES;}
 return 0;
}
static void worker(void *unused){
 Work w;for(;;){
  if(xQueueReceive(queue,&w,pdMS_TO_TICKS(100))!=pdTRUE){if(amoled_usb_armed()&&relay_until&&esp_timer_get_time()>relay_until)amoled_relay_cancel();continue;}
  bool current=live(w.epoch);unsigned state=6;taskENTER_CRITICAL(&mux);if(current)result=2;taskEXIT_CRITICAL(&mux);
  if(current){
   if(amoled_ota_busy()&&w.op!=7)state=4;
   else if(w.op==12){relay_until=esp_timer_get_time()+20000000;state=3;}
   else if(w.op==6){amoled_usb_gate(true);if(!live(w.epoch))amoled_usb_gate(false);state=amoled_usb_armed()?7:4;if(state==7)relay_until=esp_timer_get_time()+20000000;}
   else if(w.op==7){amoled_usb_gate(false);state=8;}
   else if(w.op==11||!amoled_usb_armed())state=4;
   else state=amoled_usb_execute(w.op,w.a,live,w.epoch)?3:6;
  }
  taskENTER_CRITICAL(&mux);if(epoch==w.epoch&&active)result=state;busy=false;taskEXIT_CRITICAL(&mux);
 }
}
static int access_cb(uint16_t conn,uint16_t attr,struct ble_gatt_access_ctxt *ctxt,void *arg){
 uintptr_t kind=(uintptr_t)arg;
 if(kind==4&&ctxt->op==BLE_GATT_ACCESS_OP_READ_CHR){
  const esp_app_desc_t *app=esp_app_get_description();char sha[65],json[512];amoled_hex(app->app_elf_sha256,32,sha);
  esp_ota_img_states_t image_state=ESP_OTA_IMG_UNDEFINED;esp_ota_get_state_partition(esp_ota_get_running_partition(),&image_state);
  int n=snprintf(json,sizeof(json),"{\"protocol\":1,\"device\":\"%s\",\"version\":\"%s\",\"elfSha256\":\"%s\",\"boot\":\"%s\",\"imageState\":%d,\"boardModel\":\"esp32-s3-touch-amoled-2.16\",\"usbProfile\":\"composite-fixed-v1\",\"otaSupported\":true,\"otaAuth\":\"hmac-sha256-image-v2\"}",amoled_identity_device(),app->version,sha,amoled_identity_boot(),(int)image_state);
  return n>0&&n<(int)sizeof(json)&&os_mbuf_append(ctxt->om,json,n)==0?0:BLE_ATT_ERR_INSUFFICIENT_RES;
 }
 if(kind==5){
  if(ctxt->op==BLE_GATT_ACCESS_OP_WRITE_CHR){uint8_t message[128],challenge[32];uint16_t n=0;if(OS_MBUF_PKTLEN(ctxt->om)!=32||ble_hs_mbuf_to_flat(ctxt->om,challenge,32,&n))return BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN;
   int prefix=snprintf((char*)message,sizeof(message),"PCFLASH1\n%s\n",amoled_identity_device());memcpy(message+prefix,challenge,32);auth_ready=amoled_identity_hmac(message,prefix+32,auth_proof);memset(message,0,sizeof(message));return auth_ready?0:BLE_ATT_ERR_UNLIKELY;
  }return auth_ready&&os_mbuf_append(ctxt->om,auth_proof,32)==0?0:BLE_ATT_ERR_INSUFFICIENT_AUTHEN;
 }
 if(kind==8){
  if(ctxt->op==BLE_GATT_ACCESS_OP_WRITE_CHR){uint8_t p[48];uint16_t n=0;if(OS_MBUF_PKTLEN(ctxt->om)!=48||ble_hs_mbuf_to_flat(ctxt->om,p,48,&n))return BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN;return command(conn,p);}
  char message[200],encoded[65],json[512],nonce_copy[33];uint8_t secret[32],proof[32];unsigned seq,op,state;bool running;
  taskENTER_CRITICAL(&mux);seq=sequence;op=operation;state=result;running=busy;memcpy(secret,key,32);memcpy(nonce_copy,nonce,33);taskEXIT_CRITICAL(&mux);
  unsigned hid=amoled_usb_armed(),ready=amoled_usb_ready();int n=snprintf(message,sizeof(message),"PCBLE1-ACK\n%s\n%u\n%u\n%u\n%u\n%u\n%u",nonce_copy,seq,op,state,hid,(unsigned)running,ready);
  bool ok=amoled_hmac(secret,32,message,n,proof);memset(secret,0,32);if(!ok)return BLE_ATT_ERR_UNLIKELY;amoled_hex(proof,32,encoded);
  n=snprintf(json,sizeof(json),"{\"protocol\":\"local-hid-v1\",\"nonce\":\"%s\",\"seq\":%u,\"op\":%u,\"result\":%u,\"hid\":%u,\"busy\":%u,\"ready\":%u,\"proof\":\"%s\",\"hidKeyboardProtocol\":1,\"wifiOtaSupported\":false,\"relayOnline\":%u}",nonce_copy,seq,op,state,hid,(unsigned)running,ready,encoded,amoled_relay_online());
  return n>0&&n<(int)sizeof(json)&&os_mbuf_append(ctxt->om,json,n)==0?0:BLE_ATT_ERR_INSUFFICIENT_RES;
 }return BLE_ATT_ERR_UNLIKELY;
}
static const struct ble_gatt_svc_def services[]={
 {.type=BLE_GATT_SVC_TYPE_PRIMARY,.uuid=&service_uuid.u,.characteristics=(struct ble_gatt_chr_def[]){
 {.uuid=&ctrl_uuid.u,.access_cb=amoled_ota_access,.arg=(void*)2,.flags=BLE_GATT_CHR_F_WRITE},
 {.uuid=&stat_uuid.u,.access_cb=amoled_ota_access,.arg=(void*)3,.val_handle=&amoled_ota_status_handle,.flags=BLE_GATT_CHR_F_READ|BLE_GATT_CHR_F_NOTIFY},
 {.uuid=&upgrade_uuid.u,.access_cb=amoled_ota_access,.arg=(void*)9,.flags=BLE_GATT_CHR_F_READ|BLE_GATT_CHR_F_WRITE},
 {.uuid=&info_uuid.u,.access_cb=access_cb,.arg=(void*)4,.flags=BLE_GATT_CHR_F_READ},
 {.uuid=&auth_uuid.u,.access_cb=access_cb,.arg=(void*)5,.flags=BLE_GATT_CHR_F_READ|BLE_GATT_CHR_F_WRITE},
 {.uuid=&local_uuid.u,.access_cb=access_cb,.arg=(void*)8,.flags=BLE_GATT_CHR_F_READ|BLE_GATT_CHR_F_WRITE},{0}}},{0}};
static void advertise(void);
static int gap_event(struct ble_gap_event *e,void *arg){
 if(e->type==BLE_GAP_EVENT_CONNECT){
  if(e->connect.status){advertise();return 0;}
  amoled_ota_connect(e->connect.conn_handle);
  uint8_t random[16],derived[32];char text[33],message[128];esp_fill_random(random,16);amoled_hex(random,16,text);int n=snprintf(message,sizeof(message),"PCBLE1\n%s\n%s",amoled_identity_device(),text);bool ok=amoled_identity_hmac(message,n,derived);
  taskENTER_CRITICAL(&mux);epoch++;connection=e->connect.conn_handle;active=ok;relay_until=0;sequence=operation=result=0;memcpy(nonce,text,33);memcpy(key,derived,32);auth_ready=false;taskEXIT_CRITICAL(&mux);memset(derived,0,32);
 }else if(e->type==BLE_GAP_EVENT_DISCONNECT){amoled_ota_disconnect();taskENTER_CRITICAL(&mux);active=false;connection=BLE_HS_CONN_HANDLE_NONE;auth_ready=false;memset(key,0,32);memset(auth_proof,0,32);taskEXIT_CRITICAL(&mux);amoled_relay_cancel();advertise();}
 return 0;
}
static void advertise(void){
 struct ble_hs_adv_fields f={0};f.flags=BLE_HS_ADV_F_DISC_GEN|BLE_HS_ADV_F_BREDR_UNSUP;f.uuids128=(ble_uuid128_t*)&service_uuid;f.num_uuids128=1;f.uuids128_is_complete=1;
 if(ble_gap_adv_set_fields(&f))return;
 char name[26];snprintf(name,sizeof(name),"PhoneCtl-%.12s",amoled_identity_serial());struct ble_hs_adv_fields scan={0};scan.name=(uint8_t*)name;scan.name_len=strlen(name);scan.name_is_complete=1;ble_gap_adv_rsp_set_fields(&scan);
 struct ble_gap_adv_params p={0};p.conn_mode=BLE_GAP_CONN_MODE_UND;p.disc_mode=BLE_GAP_DISC_MODE_GEN;ble_gap_adv_start(addr_type,NULL,BLE_HS_FOREVER,&p,gap_event,NULL);
}
static void on_sync(void){if(!ble_hs_util_ensure_addr(0)&&!ble_hs_id_infer_auto(0,&addr_type)){atomic_store(&synced,true);advertise();}}
static void on_reset(int reason){atomic_store(&synced,false);amoled_ota_disconnect();taskENTER_CRITICAL(&mux);active=false;connection=BLE_HS_CONN_HANDLE_NONE;taskEXIT_CRITICAL(&mux);amoled_relay_cancel();}
static void host_task(void *arg){nimble_port_run();nimble_port_freertos_deinit();}
esp_err_t amoled_relay_start(void){
 if(started)return ESP_OK;
 if(!amoled_identity_ready())return ESP_ERR_INVALID_STATE;
 queue=xQueueCreate(1,sizeof(Work));if(!queue)return ESP_ERR_NO_MEM;
 esp_err_t e=amoled_ota_init();if(e!=ESP_OK)return e;
 e=nimble_port_init();if(e!=ESP_OK){vQueueDelete(queue);queue=NULL;return e;}
 ble_hs_cfg.sync_cb=on_sync;ble_hs_cfg.reset_cb=on_reset;ble_svc_gap_init();ble_svc_gatt_init();
 if(ble_gatts_count_cfg(services)||ble_gatts_add_svcs(services))return ESP_FAIL;
 ble_svc_gap_device_name_set("PhoneCtl AMOLED");ble_att_set_preferred_mtu(517);
 if(xTaskCreate(worker,"amoled_relay",6144,NULL,4,NULL)!=pdPASS)return ESP_ERR_NO_MEM;
 started=true;nimble_port_freertos_init(host_task);return ESP_OK;
}
