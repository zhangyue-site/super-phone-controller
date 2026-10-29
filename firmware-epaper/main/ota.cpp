#include "ota.h"
#include "cloud_transport_policy.h"
#include "ota_guard.h"
#include "ota_health_policy.h"
#include "ota_transfer_budget.h"
#include "ota_resume_policy.h"
#include <strings.h>
#include <cerrno>
#include "esp_heap_caps.h"
#include "ble_ota.h"
#include "device_config.h"
#include "cloud_http_config.h"
#include "usb.h"
#include "voice.h"
#include "adb_local.h"
#include "nvs.h"
#include "esp_ota_ops.h"
#include "esp_app_desc.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "psa/crypto.h"
#include <atomic>
#include <cstdio>
#include <cstring>
static std::atomic<bool> busy(false),network_unavailable(false);
bool controller_ota_network_unavailable(){return network_unavailable.load();}
static std::atomic<int> stage(0),progress(0);
bool controller_ota_busy(){return busy;}
int controller_ota_stage(){return stage;}
int controller_ota_progress(){return progress;}
static void set_stage(int value){stage=value;controller_ota_changed();}
void controller_ota_cancel(){ota_guard_cancel(OTA_WIFI);}
struct TransferContext {
 controller::OtaTransferBudget budget;
 char range[96]={};bool range_seen=false,range_invalid=false;
 unsigned events=0;uint64_t body_bytes=0;int64_t read_window_started=0;
 TransferContext(uint32_t bytes,int64_t now):budget(bytes,now),read_window_started(now){}
 void clear_headers(){range[0]=0;range_seen=false;range_invalid=false;}
};
static int transfer_timeout(TransferContext *context){
 if(!context)return 15000;
 int64_t now=esp_timer_get_time();
 if(ota_guard_cancelled(OTA_WIFI)||context->budget.total_expired(now))return 1;
 int64_t remaining=(context->budget.budget-(now-context->budget.started))/1000;
 return remaining<15000?(remaining>0?remaining:1):15000;
}
static esp_err_t transfer_event(esp_http_client_event_t *event){
 auto *context=static_cast<TransferContext*>(event->user_data);
 if(!context)return ESP_OK;
 if(event->event_id==HTTP_EVENT_ON_HEADER&&event->header_key&&event->header_value&&!strcasecmp(event->header_key,"Content-Range")){
  if(context->range_seen||strlen(event->header_value)>=sizeof(context->range))context->range_invalid=true;
  else snprintf(context->range,sizeof(context->range),"%s",event->header_value);
  context->range_seen=true;
 }
 if(event->event_id==HTTP_EVENT_ON_DATA&&event->data_len>0){
  context->budget.received(esp_timer_get_time());++context->events;context->body_bytes+=event->data_len;
 }
 // IDF read() can make several transport reads; its body callback is the only
 // true progress clock. No worker-return timestamp may masquerade as new data.
 esp_http_client_set_timeout_ms(event->client,transfer_timeout(context));
 return ESP_OK;
}
static esp_http_client_handle_t open_url(const char *path,TransferContext *context=nullptr,bool ranged=false,unsigned offset=0){
 char url[256],auth[128];snprintf(url,sizeof(url),"%s%s",controller_ota_endpoint(),path);
 snprintf(auth,sizeof(auth),"Bearer %s",DISPLAY_TOKEN);
 esp_http_client_config_t cfg={};cfg.url=url;cfg.timeout_ms=transfer_timeout(context);controller::cloud_tls_configure(cfg);
 cfg.crt_bundle_attach=esp_crt_bundle_attach;cfg.disable_auto_redirect=true;cfg.buffer_size=4096;
 cfg.event_handler=transfer_event;cfg.user_data=context;
 auto c=esp_http_client_init(&cfg);if(!c)return nullptr;
 if(const char *host=controller::cloud_http_host()){esp_http_client_set_header(c,"Host",host);}esp_http_client_set_header(c,"Authorization",auth);
 if(ranged){char range[48];snprintf(range,sizeof(range),"bytes=%u-",offset);esp_http_client_set_header(c,"Range",range);}
 if(esp_http_client_open(c,0)!=ESP_OK){esp_http_client_cleanup(c);return nullptr;}
 if(context&&(ota_guard_cancelled(OTA_WIFI)||context->budget.total_expired(esp_timer_get_time()))){esp_http_client_cleanup(c);return nullptr;}
 esp_http_client_set_timeout_ms(c,transfer_timeout(context));
 if(esp_http_client_fetch_headers(c)<0){esp_http_client_cleanup(c);return nullptr;}
 return c;
}
static void close_url(esp_http_client_handle_t c){if(c){esp_http_client_close(c);esp_http_client_cleanup(c);}}
static bool phone_ready(){
 return controller::cloud_transport_ready(controller_voice_direct_network(),
#if CONFIG_CONTROLLER_USB_LOCAL && CONFIG_CONTROLLER_ADB_MAINTENANCE
 true,
#else
 false,
#endif
 [](){return controller_adb_network_available()||controller_adb_activate(controller_adb_ticket());});
}
static bool report(const char *phase){
 char url[256],auth[128],body[256];
 snprintf(url,sizeof(url),"%s/firmware/report",controller_ota_endpoint());
 snprintf(auth,sizeof(auth),"Bearer %s",DISPLAY_TOKEN);
 const auto *p=esp_ota_get_running_partition();esp_ota_img_states_t state=ESP_OTA_IMG_UNDEFINED;
 esp_ota_get_state_partition(p,&state);
 snprintf(body,sizeof(body),"{\"version\":\"%s\",\"slot\":\"%s\",\"phase\":\"%s\",\"imageState\":%d}",esp_app_get_description()->version,p->label,phase,(int)state);
 esp_http_client_config_t cfg={};cfg.url=url;cfg.timeout_ms=15000;controller::cloud_tls_configure(cfg);
 cfg.crt_bundle_attach=esp_crt_bundle_attach;cfg.disable_auto_redirect=true;
 auto c=esp_http_client_init(&cfg);if(!c)return false;
 esp_http_client_set_header(c,"Authorization",auth);if(const char *host=controller::cloud_http_host()){esp_http_client_set_header(c,"Host",host);}
 esp_http_client_set_header(c,"Content-Type","application/json");esp_http_client_set_method(c,HTTP_METHOD_POST);
 esp_http_client_set_post_field(c,body,strlen(body));auto err=esp_http_client_perform(c);int status=esp_http_client_get_status_code(c);
 esp_http_client_cleanup(c);ESP_LOGI("ota","Report phase=%s status=%d",phase,status);return err==ESP_OK&&status==200;
}
static void pending_report(bool value){
 nvs_handle_t n;if(nvs_open("ota",NVS_READWRITE,&n)==ESP_OK){nvs_set_u8(n,"report",value);nvs_commit(n);nvs_close(n);}
}
static void report_boot(void*){
 for(int i=0;i<3;++i){
  if(!phone_ready())ESP_LOGI("ota","Boot report deferred: WiFi unavailable; BLE maintenance remains available");
  else if(report("boot-confirmed")){pending_report(false);break;}
  vTaskDelay(pdMS_TO_TICKS(5000));
 }
 vTaskDelete(nullptr);
}
static void worker(void*){
 // Production never activates phone debugging as a hidden transport fallback.
 if(!ota_guard_cancelled(OTA_WIFI)&&!phone_ready()){
  network_unavailable=true;ESP_LOGW("ota","WiFi unavailable; use BLE upgrade, no ADB fallback");
  set_stage(5);busy=false;ota_guard_release(OTA_WIFI);vTaskDelete(nullptr);return;
 }

 esp_ota_handle_t handle=0;bool writing=false;TransferContext transfer(0,esp_timer_get_time());auto c=ota_guard_cancelled(OTA_WIFI)?nullptr:open_url("/firmware/manifest");
 unsigned size=0;char expected[65]={},version[32]={},manifest[256]={};bool ok=false;
 do{
  if(ota_guard_cancelled(OTA_WIFI)||!c||esp_http_client_get_status_code(c)!=200)break;
  int length=(int)esp_http_client_get_content_length(c);
  if(length<1||length>=sizeof(manifest))break;
  if(ota_guard_cancelled(OTA_WIFI))break;
  int got=esp_http_client_read_response(c,manifest,length);
  if(ota_guard_cancelled(OTA_WIFI)||got!=length||sscanf(manifest,"PCOTA1\n%u\n%64[0-9a-f]\n%31s",&size,expected,version)!=3||strlen(expected)!=64)break;
  close_url(c);c=nullptr;
  const auto *partition=esp_ota_get_next_update_partition(nullptr);
  if(!partition||size<1024||size>partition->size||ota_guard_cancelled(OTA_WIFI))break;
  if(!strcmp(version,esp_app_get_description()->version)){set_stage(4);ok=true;break;}
  char path[160];snprintf(path,sizeof(path),"/firmware/image?sha=%s",expected);
  if(ota_guard_cancelled(OTA_WIFI))break;
  transfer=TransferContext(size,esp_timer_get_time());
  c=open_url(path,&transfer);
  if(ota_guard_cancelled(OTA_WIFI)||!c||esp_http_client_get_status_code(c)!=200||esp_http_client_get_content_length(c)!=size)break;
  if(ota_guard_cancelled(OTA_WIFI)||esp_ota_begin(partition,size,&handle)!=ESP_OK)break;
  writing=true;set_stage(2);
  psa_crypto_init();psa_hash_operation_t hash=PSA_HASH_OPERATION_INIT;
  if(psa_hash_setup(&hash,PSA_ALG_SHA_256)!=PSA_SUCCESS)break;
  unsigned received=0;unsigned char buffer[4096];
  auto &budget=transfer.budget;controller::OtaResumePolicy recovery;
  // This opens a new read waiting window after flash preparation, without
  // claiming body bytes arrived. Later windows start only after a valid206.
  transfer.read_window_started=esp_timer_get_time();
  ESP_LOGI("ota","Transfer budget=%llds bytes=%u idle=15s budget_rate=2048B/s resume_max=3",(long long)(budget.budget/1000000),size);
  auto resume=[&]()->bool{
   close_url(c);c=nullptr;
   while(recovery.take_attempt(ota_guard_cancelled(OTA_WIFI),budget.total_expired(esp_timer_get_time()))){
    ESP_LOGW("ota","Resume attempt=%u offset=%u/%u events=%u body=%llu",recovery.attempts,received,size,transfer.events,(unsigned long long)transfer.body_bytes);
    unsigned waited=0;
    while(waited<recovery.delay_ms()&&!ota_guard_cancelled(OTA_WIFI)&&!budget.total_expired(esp_timer_get_time())){vTaskDelay(pdMS_TO_TICKS(50));waited+=50;}
    if(ota_guard_cancelled(OTA_WIFI)||budget.total_expired(esp_timer_get_time()))return false;
    transfer.clear_headers();c=open_url(path,&transfer,true,received);
    if(!c)continue;
    int status=esp_http_client_get_status_code(c);int64_t remaining=esp_http_client_get_content_length(c);
    if(transfer.range_invalid||!transfer.range_seen||!controller::ota_resume_response(status,transfer.range,remaining,received,size)){
     ESP_LOGE("ota","Reject resume status=%d length=%lld range=%s",status,(long long)remaining,transfer.range);
     close_url(c);c=nullptr;return false;
    }
    if(ota_guard_cancelled(OTA_WIFI)||budget.total_expired(esp_timer_get_time())){close_url(c);c=nullptr;return false;}
    transfer.read_window_started=esp_timer_get_time();
    ESP_LOGI("ota","Resume accepted attempt=%u offset=%u remaining=%lld",recovery.attempts,received,(long long)remaining);
    return true;
   }
   return false;
  };
  while(received<size&&!ota_guard_cancelled(OTA_WIFI)&&!budget.total_expired(esp_timer_get_time())){
   int64_t before=esp_timer_get_time();
   if(controller::ota_receive_window_expired(before,budget.last_receive,transfer.read_window_started)){
    ESP_LOGW("ota","Receive idle gap=%lldms offset=%u",(long long)((before-budget.last_receive)/1000),received);
    if(resume())continue;
    break;
   }
   errno=0;int n=esp_http_client_read(c,(char*)buffer,(size-received)>sizeof(buffer)?sizeof(buffer):size-received);
   int read_errno=errno;int64_t after=esp_timer_get_time();
   if(n<=0||after-before>=5000000)ESP_LOGW("ota","Read n=%d errno=%d took=%lldms offset=%u body_gap=%lldms events=%u body=%llu",n,read_errno,(long long)((after-before)/1000),received,(long long)((after-budget.last_receive)/1000),transfer.events,(unsigned long long)transfer.body_bytes);
   if(ota_guard_cancelled(OTA_WIFI)||budget.total_expired(after))break;
   if(n<=0){if(resume())continue;
    break;}
   if(psa_hash_update(&hash,buffer,n)!=PSA_SUCCESS)break;
   if(ota_guard_cancelled(OTA_WIFI)||budget.total_expired(esp_timer_get_time()))break;
   int64_t write_started=esp_timer_get_time();
   if(esp_ota_write(handle,buffer,n)!=ESP_OK)break;
   int64_t write_us=esp_timer_get_time()-write_started;
   if(write_us>=1000000)ESP_LOGW("ota","Flash write took=%lldms offset=%u bytes=%d",(long long)(write_us/1000),received,n);
   received+=n;int previous=progress.exchange(received*100/size);
   if(previous/10!=progress.load()/10){
    int64_t elapsed=esp_timer_get_time()-budget.started;
    ESP_LOGI("ota","Received=%u/%u elapsed=%lldms mean=%lluB/s retries=%u",received,size,(long long)(elapsed/1000),(unsigned long long)((uint64_t)received*1000000/(elapsed>0?elapsed:1)),recovery.attempts);
    controller_ota_changed();
   }
  }
  if(received<size){
   int64_t now=esp_timer_get_time();
   ESP_LOGW("ota","Transfer stopped bytes=%u/%u elapsed=%lldms body_gap=%lldms retries=%u cause=%s",received,size,(long long)((now-budget.started)/1000),(long long)((now-budget.last_receive)/1000),recovery.attempts,ota_guard_cancelled(OTA_WIFI)?"cancelled":budget.total_expired(now)?"total-deadline":recovery.attempts>=3?"resume-exhausted":"read/hash/flash/resume-rejected");
  }
  unsigned char digest[32];size_t digest_size=0;char actual[65]={};
  bool hashed=psa_hash_finish(&hash,digest,sizeof(digest),&digest_size)==PSA_SUCCESS;psa_hash_abort(&hash);
  if(hashed)for(int i=0;i<32;++i)snprintf(actual+i*2,3,"%02x",digest[i]);
  if(received!=size||ota_guard_cancelled(OTA_WIFI)||!hashed||digest_size!=32||strcmp(actual,expected))break;
  auto result=esp_ota_end(handle);writing=false;
  if(result!=ESP_OK){ESP_LOGE("ota","esp_ota_end: %s",esp_err_to_name(result));break;}
  if(ota_guard_cancelled(OTA_WIFI))break;
  esp_app_desc_t desc={};
  auto desc_err=esp_ota_get_partition_description(partition,&desc);
  ESP_LOGI("ota","Candidate version=%s expected=%s project=%s desc=%s",desc.version,version,desc.project_name,esp_err_to_name(desc_err));
  if(desc_err!=ESP_OK||strcmp(desc.version,version)||strcmp(desc.project_name,"phone_controller_epaper"))break;
  if(ota_guard_cancelled(OTA_WIFI)||!ota_guard_commit(OTA_WIFI))break;
  auto boot_err=esp_ota_set_boot_partition(partition);
  ESP_LOGI("ota","Select boot partition: %s",esp_err_to_name(boot_err));
  if(boot_err!=ESP_OK)break;
  pending_report(true);
  set_stage(3);ok=true;ESP_LOGI("ota","Verified version=%s bytes=%u slot=%s",version,size,partition->label);
 }while(false);
 close_url(c);if(writing)esp_ota_abort(handle);
 if(!ok){set_stage(5);ESP_LOGW("ota","Update failed/cancelled; active partition retained");}
 const int completed_stage=stage.load();
 if(completed_stage==3){vTaskDelay(pdMS_TO_TICKS(1500));esp_restart();}
 // All HTTP/flash handles are closed before publishing idle. Reports may block
 // on WAN, and must never own flash or mutate a later job's busy/stage fields.
 busy=false;ota_guard_release(OTA_WIFI);controller_ota_changed();
 if(!ok)report("failed");else if(completed_stage==4)report("current");
 vTaskDelete(nullptr);
}
void controller_ota_start(){
 // Acquiring the shared state publishes the job; never reset cancellation afterward.
 if(!ota_guard_acquire(OTA_WIFI))return;
 busy=true;
 network_unavailable=false;progress=0;set_stage(1);controller_voice_cancel();controller_usb_request_mode(false);controller_release();
 if(xTaskCreate(worker,"ota",12288,nullptr,3,nullptr)!=pdPASS){set_stage(5);busy=false;ota_guard_release(OTA_WIFI);}
}
static std::atomic<int64_t> input_heartbeat(0), screen_heartbeat(0);
static std::atomic<bool> screen_seen(false);
void controller_ota_input_heartbeat(){input_heartbeat=esp_timer_get_time();}
void controller_ota_screen_heartbeat(bool painted){screen_heartbeat=esp_timer_get_time();if(painted)screen_seen=true;}
void controller_ota_confirm(){
 const int64_t now=esp_timer_get_time();
 if(!controller::ota_local_health(now,screen_seen,input_heartbeat.load(),screen_heartbeat.load(),ble_ota_healthy(),heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)))return;

 static bool reported=false;
 esp_ota_img_states_t state;auto p=esp_ota_get_running_partition();
 if(esp_ota_get_state_partition(p,&state)==ESP_OK&&state==ESP_OTA_IMG_PENDING_VERIFY){
  auto err=esp_ota_mark_app_valid_cancel_rollback();if(err==ESP_OK)pending_report(true);ESP_LOGI("ota","Boot confirmed slot=%s result=%s",p->label,esp_err_to_name(err));
 }
 if(!reported){
  reported=true;nvs_handle_t n;uint8_t pending=0;
  if(nvs_open("ota",NVS_READONLY,&n)==ESP_OK){nvs_get_u8(n,"report",&pending);nvs_close(n);}
  if(pending)xTaskCreate(report_boot,"ota_boot_report",8192,nullptr,2,nullptr);
 }
}

static void health_monitor(void*){
 for(;;){
  controller_ota_confirm();
  esp_ota_img_states_t state;
  if(esp_timer_get_time()>90000000){
   if(esp_ota_get_state_partition(esp_ota_get_running_partition(),&state)==ESP_OK&&state==ESP_OTA_IMG_PENDING_VERIFY){
    ESP_LOGE("ota","Local startup health deadline failed; rollback");esp_ota_mark_app_invalid_rollback_and_reboot();
   }
   vTaskDelete(nullptr);
  }
  vTaskDelay(pdMS_TO_TICKS(1000));
 }
}
void controller_ota_health_start(){xTaskCreate(health_monitor,"ota_health",4096,nullptr,2,nullptr);}

extern "C" void controller_ota_prepare(){controller_voice_cancel();controller_usb_request_mode(false);controller_release();}
