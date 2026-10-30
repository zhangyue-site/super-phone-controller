#include "esp_http_server.h"
#include "esp_attr.h"
#include "esp_heap_caps.h"
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <atomic>
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_psram.h"
#include "esp_sntp.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "epaper_driver_bsp.h"
#include "usb.h"
#include "usb_console_policy.h"
#include "usb_proof_parse.h"
#include "device_auth.h"
#include "cJSON.h"
#include "device_config.h"
#include "cloud_http_config.h"
#ifndef DISPLAY_DEVICE_ID
#define DISPLAY_DEVICE_ID "epaper-01"
#endif
#include "boot_screen.h"
#include "mode_screens.h"
#include "mode_consent.h"
#include "tap_consent.h"
#include "diagnostics.h"
#include "usb_network.h"
#include "network_screens.h"
#include "exec_status.h"
#include "exec_strips.h"
#include "ui_assets.h"
#include "voice.h"
#include "voice_ux_policy.h"
#include "audio_feedback.h"
#include "adb_local.h"
#include "voice_screens.h"
#include "preflight.h"
#include "preparation_screens.h"
#include "touch.h"
#include "touch_ui.h"
#include "touch_screens.h"
#include "button_gesture.h"
#include "sd_store.h"
#include "ota.h"
#include "ota_guard.h"
#include "power_key_policy.h"
#include "product_screens.h"
#include "product_display_policy.h"
#include "ble_ota.h"
#include "ble_local.h"
#include "relay_display_policy.h"
#include "relay_screens.h"
#include "gesture.h"
#include "input_policy.h"
#include "voice_transport_policy.h"
#include "interaction_screens.h"
#include "esp_ota_ops.h"
#include "esp_app_desc.h"
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

static const char *TAG="controller";
static std::atomic<bool> online(false), stopped(false), stop_pending(false);
static std::atomic<unsigned> stop_sequence(0);
// Lock out all new inputs while a power request drains or USB standby persists.
static std::atomic<bool> power_locked(false),power_standby(false);
static std::atomic<int> power_view(0);
void controller_ota_changed();
static void power_show(int view){if(power_view.exchange(view)!=view)controller_ota_changed();}
#if CONFIG_TINYUSB_NET_MODE_NCM
static const int HOME_PAGE=5;
#else
static const int HOME_PAGE=4;
#endif
static std::atomic<int> page(HOME_PAGE);
static std::atomic<int64_t> consent_visible_at(0);
static std::atomic<unsigned> screen_epoch(1), painted_epoch(0);
static std::atomic<bool> painted_hid(false), screen_failed(false), screen_dirty(false), screen_painting(true);
static TaskHandle_t screen_task_handle;
static EXT_RAM_BSS_ATTR uint8_t panel_frame[5000];
static bool panel_frame_valid=false;
static portMUX_TYPE consent_mux=portMUX_INITIALIZER_UNLOCKED;
static std::atomic<int> consent_step(0);
static std::atomic<int64_t> consent_deadline(0);
static void go_page(int target){
 taskENTER_CRITICAL(&consent_mux);
 if(target!=2||page.load()!=2){consent_step=0;consent_deadline=0;}
 consent_visible_at=0;screen_epoch.fetch_add(1);page=target;
 controller_event("page",target);
 taskEXIT_CRITICAL(&consent_mux);
 screen_dirty=true;if(screen_task_handle)xTaskNotifyGive(screen_task_handle);
}
void controller_ota_changed(){screen_dirty=true;if(screen_task_handle)xTaskNotifyGive(screen_task_handle);}
static std::atomic<int> exec_view(controller::EXEC_NO_USB);
static std::atomic<bool> exec_failed(false);
void controller_exec_show(int code){
 if(code<controller::EXEC_READY||code>controller::EXEC_FAILED)code=controller::EXEC_FAILED;
 if(exec_view.exchange(code)!=code)controller_ota_changed();
}
void controller_exec_fail(){exec_failed=true;controller_exec_show(controller::EXEC_FAILED);}
void controller_exec_clear(){exec_failed=false;}
bool controller_exec_failed(){return exec_failed.load();}

static char ssid[33],password[65];
static int network_slot=0,retries=0;
static std::atomic<bool> wifi_enabled(false);
static bool wifi_initialized=false,sntp_started=false;
static std::atomic<int> check_server(controller::WAIT),check_chat(controller::WAIT),check_asr(controller::WAIT);
static std::atomic<bool> wifi_connected(false);
#if CONFIG_TINYUSB_NET_MODE_NCM
static const int PAGE_COUNT=5;
#else
static const int PAGE_COUNT=4;
#endif
void controller_net_changed(){online=wifi_connected.load()||controller_usb_net_has_ip()||controller_adb_network_available();screen_dirty=true;}
void controller_usb_disconnected(){
 controller_adb_cancel();controller_voice_cancel();stop_pending=true;
 taskENTER_CRITICAL(&consent_mux);
 controller_usb_request_mode(false);controller_release();go_page(HOME_PAGE);
 taskEXIT_CRITICAL(&consent_mux);
}


static bool load_wifi(int slot){
 nvs_handle_t h;
 if(nvs_open("wifi",NVS_READONLY,&h)!=ESP_OK)return false;
 char skey[16],pkey[16];
 if(slot==0){strcpy(skey,"ssid");strcpy(pkey,"password");}
 else {snprintf(skey,sizeof(skey),"ssid%d",slot);snprintf(pkey,sizeof(pkey),"password%d",slot);}
 size_t n=sizeof(ssid),p=sizeof(password);
 esp_err_t err=nvs_get_str(h,skey,ssid,&n);
 password[0]=0;nvs_get_str(h,pkey,password,&p);nvs_close(h);
 return err==ESP_OK && ssid[0];
}
static void connect_saved(){
 if(!load_wifi(network_slot)){network_slot=0;if(!load_wifi(0)){ESP_LOGW(TAG,"No saved WiFi; configure using USB WIFI command");return;}}
 wifi_config_t cfg={};
 memcpy(cfg.sta.ssid,ssid,strlen(ssid));memcpy(cfg.sta.password,password,strlen(password));
 cfg.sta.pmf_cfg.capable=true;
 ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA,&cfg));
 esp_wifi_connect();
}
static void wifi_event(void*,esp_event_base_t base,int32_t id,void* event_data){
 if(!wifi_enabled){wifi_connected=false;online=controller_usb_net_has_ip();return;}
 if(base==IP_EVENT && id==IP_EVENT_STA_GOT_IP){auto *got=static_cast<ip_event_got_ip_t*>(event_data);esp_err_t route=esp_netif_set_default_netif(got->esp_netif);ESP_LOGI(TAG,"WiFi default route result=%s",esp_err_to_name(route));wifi_connected=true;online=true;retries=0;ESP_LOGI(TAG,"WiFi connected");if(screen_task_handle)xTaskNotifyGive(screen_task_handle);}
 else if(base==WIFI_EVENT && id==WIFI_EVENT_STA_DISCONNECTED){wifi_connected=false;online=controller_usb_net_has_ip(); if(++retries>=3){retries=0;network_slot=(network_slot+1)%10;connect_saved();}else esp_wifi_connect();}
 else if(base==WIFI_EVENT && id==WIFI_EVENT_STA_START)connect_saved();
}
static void wifi_start(){
 if(wifi_enabled.exchange(true))return;
 esp_err_t err=ESP_OK;
 if(wifi_initialized){err=esp_wifi_start();if(err!=ESP_OK)wifi_enabled=false;return;}
 static esp_netif_t *wifi_netif=nullptr;
 if(!wifi_netif)wifi_netif=esp_netif_create_default_wifi_sta();
 if(!wifi_netif){wifi_enabled=false;controller_usb_write("WIFI ERROR netif allocation failed\r\n");return;}
 wifi_init_config_t init=WIFI_INIT_CONFIG_DEFAULT();
 err=esp_wifi_init(&init);
 if(err!=ESP_OK){wifi_enabled=false;ESP_LOGE(TAG,"WiFi init failed: %s internal=%u largest=%u",esp_err_to_name(err),(unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT),(unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));controller_usb_write("WIFI ERROR init failed; inspect LOGS\r\n");return;}
 wifi_initialized=true;
 err=esp_wifi_set_storage(WIFI_STORAGE_RAM);
 if(err==ESP_OK)err=esp_event_handler_register(WIFI_EVENT,ESP_EVENT_ANY_ID,wifi_event,nullptr);
 if(err==ESP_OK)err=esp_event_handler_register(IP_EVENT,IP_EVENT_STA_GOT_IP,wifi_event,nullptr);
 if(err==ESP_OK)err=esp_wifi_set_mode(WIFI_MODE_STA);
 if(err==ESP_OK)err=esp_wifi_start();
 if(err!=ESP_OK){wifi_enabled=false;ESP_LOGE(TAG,"WiFi start failed: %s",esp_err_to_name(err));controller_usb_write("WIFI ERROR start failed; inspect LOGS\r\n");}
}
static const char *server_endpoint(){
 if(wifi_connected)return DISPLAY_ENDPOINT;
#if CONFIG_CONTROLLER_USB_LOCAL && CONFIG_CONTROLLER_ADB_MAINTENANCE
 if(controller_adb_network_available())return "https://127.0.0.1:18843/phone-controller";
#endif
 return DISPLAY_ENDPOINT;
}
const char *controller_ota_endpoint(){
 if(wifi_connected)return DISPLAY_ENDPOINT;
#if CONFIG_CONTROLLER_USB_LOCAL && CONFIG_CONTROLLER_ADB_MAINTENANCE
 if(controller_adb_network_available())return "https://127.0.0.1:18843/phone-controller";
 if(controller_usb_net_peer())return "https://192.168.77.2:18843/phone-controller";
#endif
 return DISPLAY_ENDPOINT;
}
static bool request(const char *path,uint8_t *out){
 char url[256],auth[128];snprintf(url,sizeof(url),"%s%s",server_endpoint(),path);
 snprintf(auth,sizeof(auth),"Bearer %s",DISPLAY_TOKEN);
 esp_http_client_config_t cfg={};cfg.url=url;cfg.timeout_ms=8000;
 controller::cloud_tls_configure(cfg);
 cfg.crt_bundle_attach=esp_crt_bundle_attach;cfg.buffer_size=2048;cfg.disable_auto_redirect=true;
 esp_http_client_handle_t client=esp_http_client_init(&cfg);if(!client)return false;
 esp_http_client_set_header(client,"Authorization",auth);
 if(const char *host=controller::cloud_http_host()){esp_http_client_set_header(client,"Host",host);}
 if(!out){
  esp_http_client_set_method(client,HTTP_METHOD_POST);
  char seq[16];snprintf(seq,sizeof(seq),"%u",controller_voice_cancel_sequence());
  esp_http_client_set_header(client,"X-Voice-UI","plan-v1");esp_http_client_set_header(client,"X-Voice-Session",controller_voice_session());esp_http_client_set_header(client,"X-Voice-Sequence",seq);
 }
 esp_err_t err=esp_http_client_open(client,0);
 int total=0,status=0;
 if(err==ESP_OK){
  int64_t length=esp_http_client_fetch_headers(client);
  status=esp_http_client_get_status_code(client);
  if(out && status==200 && length==5000){
   while(total<5000){int n=esp_http_client_read(client,(char*)out+total,5000-total);if(n<=0)break;total+=n;}
  }
 }
 esp_http_client_close(client);esp_http_client_cleanup(client);
 bool ok=err==ESP_OK && status==200 && (!out || total==5000);
 controller_usb_net_backend(ok);
 if(!ok)ESP_LOGW(TAG,"Display request failed status=%d bytes=%d error=%s",status,total,esp_err_to_name(err));
 return ok;
}
// Operation telemetry is separate from free-form ESP logs/user content.
static void upload_events(){
 if(controller_ota_busy())return;
 if(controller_voice_conversing() || controller_voice_stage()==10 || controller_voice_stage()==11)return;
 if(!online || controller_voice_stage()==1 || controller_voice_stage()==2 || controller_voice_stage()==4 || controller_voice_stage()==7)return;
 static char body[4097];size_t size=controller_events_snapshot(body,sizeof(body));if(!size)return;
 char url[256],auth[128];snprintf(url,sizeof(url),"%s/events",server_endpoint());snprintf(auth,sizeof(auth),"Bearer %s",DISPLAY_TOKEN);
 esp_http_client_config_t cfg={};cfg.url=url;cfg.timeout_ms=5000;controller::cloud_tls_configure(cfg);
 cfg.crt_bundle_attach=esp_crt_bundle_attach;cfg.disable_auto_redirect=true;
 esp_http_client_handle_t client=esp_http_client_init(&cfg);if(!client)return;
 esp_http_client_set_header(client,"Authorization",auth);if(const char *host=controller::cloud_http_host()){esp_http_client_set_header(client,"Host",host);}
 esp_http_client_set_header(client,"Content-Type","application/x-ndjson");esp_http_client_set_method(client,HTTP_METHOD_POST);
 esp_http_client_set_post_field(client,body,size);
 esp_err_t err=esp_http_client_perform(client);int status=esp_http_client_get_status_code(client);
 esp_http_client_cleanup(client);
 ESP_LOGI(TAG,"Operation log upload status=%d ok=%d",status,err==ESP_OK&&status==200);
}
static bool paint(epaper_driver_display &display,const uint8_t *frame,bool full){
 for(int y=0;y<200;y++)for(int x=0;x<200;x++)
  display.EPD_DrawColorPixel(x,y,frame[y*25+x/8]&(0x80>>(x%8))?255:0);
 if(full){display.EPD_Init();display.EPD_DisplayPartBaseImage();display.EPD_Init_Partial();}
 else display.EPD_DisplayPart();
 return display.healthy();
}
// Clock uses UTC+8 explicitly; never display a fabricated time before SNTP sync.
[[maybe_unused]] static void draw_footer(uint8_t *frame,int mode){
 memset(frame+176*25,255,24*25);
 time_t utc=time(nullptr);
 if(utc>=1704067200){
  time_t china=utc+8*3600;struct tm local={};gmtime_r(&china,&local);
  char stamp[20];strftime(stamp,sizeof(stamp),"%Y-%m-%d %H:%M",&local);
  for(unsigned i=0;stamp[i];++i){
   const char *alphabet="0123456789-: ";
   const char *found=strchr(alphabet,stamp[i]);
   unsigned glyph=found?found-alphabet:12;
   for(int y=0;y<12;++y)frame[(176+y)*25+1+i]=clock_glyphs[glyph][y];
  }
 }else memcpy(frame+176*25,clock_unknown,300);
 memcpy(frame+188*25,mode==2?check_hint:mode==1?voice_hint:footer_hint,300); // Two full twelve-row lines fit below the controls.
}
bool controller_voice_online(){return online.load()&&!stop_pending.load();}
static EXT_RAM_BSS_ATTR uint8_t dialogue_frame[5000];
static std::atomic<bool> dialogue_frame_valid(false);
static portMUX_TYPE dialogue_mux=portMUX_INITIALIZER_UNLOCKED;
static std::atomic<unsigned> dialogue_revision(0),dialogue_painted_revision(0),dialogue_painted_epoch(0);
static std::atomic<int64_t> dialogue_presented_at(0);
int64_t controller_dialogue_visible_ms(unsigned revision){return revision&&dialogue_painted_revision.load()==revision&&dialogue_painted_epoch.load()==screen_epoch.load()&&page.load()==PAGE_COUNT-1&&!screen_failed?(esp_timer_get_time()-dialogue_presented_at.load())/1000:-1;}
void controller_dialogue_screen(const unsigned char *frame,unsigned revision){
 taskENTER_CRITICAL(&dialogue_mux);
 dialogue_frame_valid=frame!=nullptr;dialogue_revision=revision;if(!frame)dialogue_painted_revision=0;
 if(frame)memcpy(dialogue_frame,frame,5000);
 taskEXIT_CRITICAL(&dialogue_mux);screen_dirty=true;
}
static bool dialogue_copy(uint8_t *frame,unsigned *revision=nullptr){
 taskENTER_CRITICAL(&dialogue_mux);bool valid=dialogue_frame_valid;if(valid){memcpy(frame,dialogue_frame,5000);if(revision)*revision=dialogue_revision.load();}taskEXIT_CRITICAL(&dialogue_mux);return valid;
}
void controller_voice_changed(bool completed){
 // Local completion feedback avoids another TLS round-trip for a 5000-byte screen.
 if(completed)ESP_LOGI(TAG,"Voice recognized; local result shown without fetching task bitmap");
 screen_dirty=true;
}
static std::atomic<int> voice_http_status(0);
int controller_voice_last_http_status(){return voice_http_status.load();}
bool controller_voice_upload(const unsigned char *pcm,unsigned size,unsigned sequence){
 voice_http_status=0;
 char url[256],auth[128];snprintf(url,sizeof(url),"%s/voice",server_endpoint());
 snprintf(auth,sizeof(auth),"Bearer %s",DISPLAY_TOKEN);
 esp_http_client_config_t cfg={};cfg.url=url;cfg.timeout_ms=80000;
 controller::cloud_tls_configure(cfg);cfg.crt_bundle_attach=esp_crt_bundle_attach;cfg.disable_auto_redirect=true;
 auto client=esp_http_client_init(&cfg);if(!client)return false;
 esp_http_client_set_header(client,"Authorization",auth);if(const char *host=controller::cloud_http_host()){esp_http_client_set_header(client,"Host",host);}
 char seq[16];snprintf(seq,sizeof(seq),"%u",sequence);
 esp_http_client_set_header(client,"X-Voice-UI","plan-v1");esp_http_client_set_header(client,"X-Voice-Session",controller_voice_session());esp_http_client_set_header(client,"X-Voice-Sequence",seq);
 esp_http_client_set_header(client,"Content-Type","application/octet-stream");esp_http_client_set_header(client,"X-Voice-Dialogue","1");esp_http_client_set_method(client,HTTP_METHOD_POST);
 esp_err_t err=esp_http_client_open(client,size);unsigned sent=0;
 if(err==ESP_OK){
  while(sent<size&&controller_voice_cancel_sequence()<sequence){int n=esp_http_client_write(client,(const char*)pcm+sent,size-sent);if(n<=0)break;sent+=n;}
 }
 int status=0;if(sent==size && esp_http_client_fetch_headers(client)>=0)status=esp_http_client_get_status_code(client);
 esp_http_client_close(client);esp_http_client_cleanup(client);
 voice_http_status=status;ESP_LOGI(TAG,"Voice upload bytes=%u/%u status=%d",sent,size,status);return status==200&&controller_voice_cancel_sequence()<sequence;
}
bool controller_voice_stream_upload(VoiceStream &stream){
 char url[256],auth[128],seq[16];snprintf(url,sizeof(url),"%s/voice/stream",server_endpoint());
 snprintf(auth,sizeof(auth),"Bearer %s",DISPLAY_TOKEN);snprintf(seq,sizeof(seq),"%u",stream.sequence);
 esp_http_client_config_t cfg={};cfg.url=url;cfg.timeout_ms=15000;controller::cloud_tls_configure(cfg);
 cfg.crt_bundle_attach=esp_crt_bundle_attach;cfg.disable_auto_redirect=true;
 auto client=esp_http_client_init(&cfg);if(!client)return false;
 esp_http_client_set_header(client,"Authorization",auth);if(const char *host=controller::cloud_http_host()){esp_http_client_set_header(client,"Host",host);}
 esp_http_client_set_header(client,"X-Voice-UI","plan-v1");esp_http_client_set_header(client,"X-Voice-Session",controller_voice_session());esp_http_client_set_header(client,"X-Voice-Sequence",seq);
 esp_http_client_set_header(client,"Content-Type","application/octet-stream");esp_http_client_set_header(client,"X-Voice-Dialogue","1");esp_http_client_set_method(client,HTTP_METHOD_POST);
 int64_t began=esp_timer_get_time(),first=0;bool ok=esp_http_client_open(client,-1)==ESP_OK;unsigned sent=0;
 auto write=[&](const char *p,unsigned n){return !stream.abort&&esp_http_client_write(client,p,n)==(int)n;};
 while(ok&&!stream.abort){
  unsigned available=stream.bytes.load();
  if(available>sent&&(available-sent>=3200||stream.done)){
   unsigned size=available-sent;if(size>3200)size=3200;char header[16];int n=snprintf(header,sizeof(header),"%x\r\n",size);
   ok=write(header,n)&&write((const char*)stream.pcm+sent,size)&&write("\r\n",2);
   if(ok){sent+=size;if(!first)first=esp_timer_get_time();}
  }else if(stream.done&&available==sent)break;
  else vTaskDelay(pdMS_TO_TICKS(10));
 }
 ok=ok&&!stream.abort&&sent>=12800;
 if(ok)ok=write("0\r\n\r\n",5);
 int status=0;
 if(ok){esp_http_client_set_timeout_ms(client,80000);if(esp_http_client_fetch_headers(client)>=0)status=esp_http_client_get_status_code(client);}
 esp_http_client_close(client);esp_http_client_cleanup(client);
 ESP_LOGI(TAG,"Voice stream bytes=%u first_ms=%lld total_ms=%lld status=%d",sent,(long long)(first?(first-began)/1000:-1),(long long)((esp_timer_get_time()-began)/1000),status);
 controller_event("upload",page.load(),first?(first-began)/1000:-1,stream.finished_at?(esp_timer_get_time()-stream.finished_at)/1000:-1,status);
 return ok&&status==200&&!stream.abort;
}
bool controller_preflight_probe(){
 if(!online)return false;
 check_server=controller::RUN;check_chat=check_asr=controller::WAIT;screen_dirty=true;
 char url[256],auth[128];snprintf(url,sizeof(url),"%s/checks.bin",server_endpoint());
 snprintf(auth,sizeof(auth),"Bearer %s",DISPLAY_TOKEN);
 esp_http_client_config_t cfg={};cfg.url=url;cfg.timeout_ms=120000;controller::cloud_tls_configure(cfg);
 cfg.crt_bundle_attach=esp_crt_bundle_attach;cfg.disable_auto_redirect=true;
 auto client=esp_http_client_init(&cfg);if(!client){check_server=controller::FAILED;return false;}
 esp_http_client_set_header(client,"Authorization",auth);if(const char *host=controller::cloud_http_host()){esp_http_client_set_header(client,"Host",host);}
 esp_http_client_set_method(client,HTTP_METHOD_POST);
 char flags[3]={};int size=0;bool ok=esp_http_client_open(client,0)==ESP_OK;
 if(ok && esp_http_client_fetch_headers(client)==3 && esp_http_client_get_status_code(client)==200){
  while(size<3){int n=esp_http_client_read(client,flags+size,3-size);if(n<=0)break;size+=n;}
 }
 esp_http_client_close(client);esp_http_client_cleanup(client);
 ok=size==3;for(int i=0;i<3;++i)ok=ok&&(flags[i]=='1'||flags[i]=='2');
 check_server=ok?(flags[0]=='1'?controller::DONE:controller::FAILED):controller::FAILED;
 check_chat=ok?(flags[1]=='1'?controller::DONE:controller::FAILED):controller::WAIT;
 check_asr=ok?(flags[2]=='1'?controller::DONE:controller::FAILED):controller::WAIT;
 screen_dirty=true;return ok && flags[0]=='1' && flags[1]=='1' && flags[2]=='1';
}
static auto current_preflight(){
 controller::PreflightInput input={controller_usb_ready(),controller_usb_net_peer()!=0,controller_adb_stage(),
  controller_usb_net_has_ip()||controller_adb_network_available(),(controller::CheckStatus)check_server.load(),(controller::CheckStatus)check_chat.load(),(controller::CheckStatus)check_asr.load()};
 return controller::preflight(input);
}
bool controller_voice_direct_network(){return wifi_connected.load();}
bool controller_voice_prepared(){return online && controller::voice_ready(wifi_connected.load(),current_preflight()[7]==controller::DONE,
 check_server==controller::DONE,check_chat==controller::DONE,check_asr==controller::DONE);}
static void preparation(uint8_t *frame){
#if !CONFIG_CONTROLLER_ADB_MAINTENANCE
 if(!wifi_connected){memcpy(frame,product_offline[0],5000);return;}
#endif
 if(wifi_connected){int status=check_server==controller::FAILED||check_chat==controller::FAILED||check_asr==controller::FAILED?1:controller_voice_prepared()?2:0;
  memcpy(frame,product_prepare[status],5000);return;}
#if CONFIG_CONTROLLER_ADB_MAINTENANCE
 int adb_error=controller_adb_error();
 if(adb_error>0&&adb_error<8){memcpy(frame,interaction_adb_error[adb_error],5000);return;}
 auto rows=current_preflight();memset(frame,255,5000);
 int step=0;while(step<7 && rows[step]==controller::DONE)++step;
 // The tiny display shows one actual current step at readable size, not eight small rows.
 memcpy(frame,preparation_base,31*25);
 if(rows[7]==controller::DONE)memcpy(frame,assistant_online,sizeof(assistant_online));
 memcpy(frame+44*25,focus_titles[step],sizeof(focus_titles[step]));
 memcpy(frame+82*25,focus_status[rows[step]],sizeof(focus_status[0]));
 memcpy(frame+122*25,focus_hints[step],sizeof(focus_hints[step]));
#else
 // Wi-Fi can disconnect between the two atomic reads above. Never reveal legacy setup.
 memcpy(frame,product_offline[0],5000);
#endif
}
void controller_diagnostic_state(char *out,unsigned size){
 snprintf(out,size,"{\"usb\":%d,\"peer\":%d,\"adb\":%d,\"adbError\":%d,\"net\":%d,\"online\":%d,\"server\":%d,\"chat\":%d,\"asr\":%d,\"hid\":%d,\"wifi\":%d,\"page\":%d,\"voice\":%d,\"screenError\":%d}",
 controller_usb_ready(),controller_usb_net_peer()!=0,controller_adb_stage(),controller_adb_error(),controller_usb_net_stage(),online.load(),check_server.load(),check_chat.load(),check_asr.load(),controller_usb_hid_enabled(),wifi_enabled.load(),page.load(),controller_voice_stage(),screen_failed.load());
}
extern "C" void controller_ble_diagnostic_state(char *out,unsigned size){controller_diagnostic_state(out,size);}
static EXT_RAM_BSS_ATTR uint8_t cached_screens[2][5000];
static bool cached_valid[2]={false,false};
static portMUX_TYPE cache_mux=portMUX_INITIALIZER_UNLOCKED;
static void telemetry_task(void*){
 auto *fresh=(uint8_t*)malloc(5000);
 for(;;){
  if(!controller_ota_busy()&&controller_voice_background_http_begin()){
   if(online && stop_pending.exchange(false) && !request("/stop",nullptr))stop_pending=true;
   int selected=page.load();
   if(online&&fresh&&(selected==0||selected==1)){
    char path[48];snprintf(path,sizeof(path),"/screen.bin?page=%d",selected);
    if(request(path,fresh)){
     taskENTER_CRITICAL(&cache_mux);memcpy(cached_screens[selected],fresh,5000);cached_valid[selected]=true;taskEXIT_CRITICAL(&cache_mux);
     if(page==selected)controller_ota_changed();
    }
   }
   upload_events();
   controller_voice_background_http_end();
  }
  vTaskDelay(pdMS_TO_TICKS(5000));
 }
}
static void screen_task(void*){
 custom_lcd_spi_t pins={11,10,9,8,13,12,SPI3_HOST,5000};
 epaper_driver_display display(200,200,pins);
 auto *buffers=(uint8_t*)heap_caps_calloc(2,5000,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
 configASSERT(buffers);uint8_t *frame=buffers,*previous=buffers+5000;
 int refreshes=0;unsigned previous_epoch=0;int64_t last_recording_paint=0;
 for(;;){
  const unsigned epoch=screen_epoch.load();
  const int current_page=page.load();
  const bool hid=controller_usb_hid_enabled();
  static bool seen_usb=false;
  const bool usb_present=controller_usb_ready();
  const int home_view=controller::product_home_state(usb_present,hid,online.load(),controller_ble_local_connected(),stopped.load(),controller_exec_failed(),seen_usb);
  seen_usb=seen_usb||usb_present;
  bool success=false;unsigned visible_revision=0;
  ble_ota_state_t ble_state;uint8_t ble_progress,ble_error;
  ble_ota_status(&ble_state,&ble_progress,&ble_error);
  if(ble_ota_busy()||ble_state==BLE_OTA_READY){
   memcpy(frame,product_ble[(int)ble_state],5000);
   for(int y=143;y<151;++y)for(int x=8;x<192;++x)
    if(y==143||y==150||x==8||x==191||x<8+184*controller::product_progress(ble_progress)/100)frame[y*25+x/8]&=~(0x80>>(x%8));
  }else if(controller_ota_busy()||current_page==HOME_PAGE+5){
   if(controller_ota_stage()==5&&controller_ota_network_unavailable())memcpy(frame,product_ota_offline[0],5000);
   else memcpy(frame,product_ota[controller_ota_stage()],5000);
  }else if(current_page==HOME_PAGE){
   memcpy(frame,product_home[home_view],5000);
  }else if(current_page==HOME_PAGE+1){
   memcpy(frame,product_manual[0],5000);
  }else if(current_page==HOME_PAGE+2){
   memcpy(frame,product_manual[1],5000);
  }else if(current_page==HOME_PAGE+3){
   memcpy(frame,product_manual[2],5000);
  }else if(current_page==HOME_PAGE+4){
   memcpy(frame,product_manual[3],5000);
  }else if(current_page==HOME_PAGE+6){
   memcpy(frame,product_sound[(controller_audio_muted()?6:0)+controller_audio_volume()/20],5000);
  }else if(current_page==2){
   memcpy(frame,product_mode[(hid?2:0)+consent_step.load()],5000);
  }else if(current_page==PAGE_COUNT-1){
   int voice=controller_voice_stage();
   bool result_shown=(voice==10||voice==11||voice==3||voice==5)&&dialogue_copy(frame,&visible_revision);
   if(!result_shown){
#if CONFIG_CONTROLLER_USB_LOCAL
   if((voice>=7&&voice<=9) || voice==0 || voice==6){if(controller_voice_prepared())memcpy(frame,product_voice[0],5000);else preparation(frame);}
   else memcpy(frame,product_voice[(voice>=0&&voice<14)?voice:5],5000);
#else
   memcpy(frame,product_voice[(voice>=0&&voice<14)?voice:5],5000);
#endif
   }
  }else if(current_page==3){
   int state=controller::product_network_state(controller_usb_ready(),wifi_connected.load(),controller_ble_local_connected());memcpy(frame,product_network[state],5000);
  }else{
   int selected=current_page==1?1:0;
   taskENTER_CRITICAL(&cache_mux);
   success=cached_valid[selected];if(success)memcpy(frame,cached_screens[selected],5000);
   taskEXIT_CRITICAL(&cache_mux);
   if(!success)memcpy(frame,product_loading[selected],5000);
   else memcpy(frame,product_cache_title[selected],sizeof(product_cache_title[0]));
  }
  if(current_page==PAGE_COUNT-1&&controller_voice_stage()==1){
   auto black=[&](int x,int y){if(x>=0&&x<200&&y>=0&&y<162)frame[y*25+x/8]&=~(0x80>>(x%8));};
   const unsigned char segments[10]={0x3f,0x06,0x5b,0x4f,0x66,0x6d,0x7d,0x07,0x7f,0x6f};
   auto digit=[&](int x,int n){int seg=segments[n%10];for(int q=0;q<7;++q)if(seg&(1<<q)){int xx=x,yy=54,w=10,h=2;switch(q){case 1:xx+=9;yy+=1;w=2;h=10;break;case 2:xx+=9;yy+=11;w=2;h=10;break;case 3:yy+=20;break;case 4:yy+=11;w=2;h=10;break;case 5:yy+=1;w=2;h=10;break;case 6:yy+=10;break;}for(int y=yy;y<yy+h;++y)for(int a=xx;a<xx+w;++a)black(a,y);}};
   unsigned seconds=controller_voice_recorded_ms()/1000;digit(62,seconds/10);digit(76,seconds%10);
   unsigned level=controller_voice_level();if(level>2000)level=2000;level=(level/400)*400;int fill=142*level/2000;
   for(int y=136;y<149;++y)for(int x=48;x<192;++x)if(y==136||y==148||x==48||x==191||x<49+fill)black(x,y);
  }
  // A visible STOP always matches the unchanged right-hand footer hit area.
  // OTA and power pages retain their own honest busy footer (HOME is unavailable).
  if(!(ble_ota_busy()||ble_state==BLE_OTA_READY||controller_ota_busy()||current_page==HOME_PAGE+5))
  {
   int feedback=stopped?5:exec_view.load();if(feedback<0||feedback>5)feedback=4;
   memcpy(frame+162*25,product_footer[feedback],sizeof(product_footer[0]));
  }
  if((controller_ota_busy()||current_page==HOME_PAGE+5)&&controller_ota_stage()==2){
   const unsigned progress=controller::product_progress(controller_ota_progress());
   for(int y=143;y<151;++y)for(int x=8;x<192;++x)
    if(y==143||y==150||x==8||x==191||x<8+184*progress/100)frame[y*25+x/8]&=~(0x80>>(x%8));
  }
  memset(frame+188*25,255,12*25); // Keep tiny build metadata off the 1.54-inch display.
  if(power_view.load()>0)memcpy(frame,product_power[power_view.load()-1],5000);
  if(epoch!=screen_epoch.load() || current_page!=page.load())continue;
  if(memcmp(frame,previous,5000) || previous_epoch!=epoch){
   // Recording counters/level update at most once a second; STOP/page/state changes bypass this.
   if(current_page==PAGE_COUNT-1&&controller_voice_stage()==1&&previous_epoch==epoch&&last_recording_paint&&esp_timer_get_time()-last_recording_paint<1000000){
    ulTaskNotifyTake(pdTRUE,pdMS_TO_TICKS(100));continue;
   }
   if(current_page==PAGE_COUNT-1&&controller_voice_stage()==1)last_recording_paint=esp_timer_get_time();else last_recording_paint=0;
   screen_painting=true;
   if(!paint(display,frame,refreshes++%20==0)){
    consent_visible_at=0;screen_failed=true;
    ESP_LOGE(TAG,"Screen disabled after driver fault; USB recovery remains available");
    esp_ota_img_states_t state;auto running=esp_ota_get_running_partition();
    if(esp_ota_get_state_partition(running,&state)==ESP_OK&&state==ESP_OTA_IMG_PENDING_VERIFY)esp_ota_mark_app_invalid_rollback_and_reboot();
    vTaskSuspend(nullptr);
   }
   memcpy(previous,frame,5000);previous_epoch=epoch;
   taskENTER_CRITICAL(&consent_mux);
   if(epoch==screen_epoch.load() && current_page==page.load()){
    painted_epoch=epoch;memcpy(panel_frame,frame,5000);panel_frame_valid=true;
   }
   if(current_page==2 && epoch==screen_epoch.load() && page==2){
    painted_hid=hid;painted_epoch=epoch;
    consent_visible_at=esp_timer_get_time()/1000;
   if(!consent_deadline.load())consent_deadline=consent_visible_at.load()+15000;
   }
   taskEXIT_CRITICAL(&consent_mux);
   if(visible_revision&&current_page==PAGE_COUNT-1&&epoch==screen_epoch.load()&&visible_revision==dialogue_revision.load()){
    dialogue_painted_epoch=epoch;dialogue_presented_at=esp_timer_get_time();dialogue_painted_revision=visible_revision;
   }
   screen_painting=false;
   controller_ota_screen_heartbeat(true);
   ESP_LOGI(TAG,"Screen updated page=%d",current_page);controller_event("page",current_page,0,0,1);
  }
  if(visible_revision&&dialogue_painted_revision.load()!=visible_revision&&current_page==PAGE_COUNT-1&&epoch==screen_epoch.load()&&previous_epoch==epoch&&!memcmp(frame,previous,5000)){
   dialogue_painted_epoch=epoch;dialogue_presented_at=esp_timer_get_time();dialogue_painted_revision=visible_revision;
  }
  controller_ota_screen_heartbeat(false);
  ulTaskNotifyTake(pdTRUE,pdMS_TO_TICKS(5000));
 }
}
static void stop_now(){
 stop_sequence.fetch_add(1);
 controller_event("stop",page.load());
 taskENTER_CRITICAL(&consent_mux);
 controller_ble_local_cancel();ble_ota_cancel();controller_ota_cancel();controller_adb_cancel();controller_voice_cancel();controller_audio_interrupt();stopped=true;stop_pending=true;controller_release();controller_usb_request_mode(false);go_page(1);
 taskEXIT_CRITICAL(&consent_mux);
 if(screen_task_handle)xTaskNotifyGive(screen_task_handle);
 ESP_LOGI(TAG,"Local stop latched; no actuator enabled");
}
bool controller_ble_hid_arm(bool (*live)(unsigned),unsigned epoch){
 bool ok=false;taskENTER_CRITICAL(&consent_mux);
 if(!power_locked.load()&&live(epoch)&&!controller_voice_transport_busy()&&!controller_ota_busy()&&!ble_ota_busy()&&!screen_failed){
  controller_voice_cancel();controller_adb_cancel();controller_release();stopped=false;
  controller_usb_request_mode(true);go_page(HOME_PAGE+1);ok=true;
 }
 taskEXIT_CRITICAL(&consent_mux);
 if(ok&&screen_task_handle){xTaskNotifyGive(screen_task_handle);}
 return ok;
}
void controller_ble_hid_stop(){stop_now();}
static void touch_action(controller::TouchTarget target,int64_t began,int64_t now){
 using controller::TouchTarget;
 if(power_locked.load())return;
 controller_event("action",page.load(),(int)target);
 switch(target){
 case TouchTarget::SOUND_SETTINGS:go_page(HOME_PAGE+6);break;
 case TouchTarget::VOLUME_DOWN:controller_audio_adjust(-20);controller_ota_changed();break;
 case TouchTarget::VOLUME_UP:controller_audio_adjust(20);controller_ota_changed();break;
 case TouchTarget::MUTE:controller_audio_toggle_mute();controller_ota_changed();break;
 case TouchTarget::SOUND_TEST:controller_audio_prompt(controller::SpeechPrompt::TEST);break;
 case TouchTarget::UPDATE:controller_ota_start();screen_dirty=true;break;
 case TouchTarget::START:
  if(controller_voice_conversing()){stop_now();go_page(HOME_PAGE);break;}
  go_page(PAGE_COUNT-1);
  stopped=false; // A tap opens the hold-to-talk screen; it never starts open-mic capture.
  break;
 case TouchTarget::HOME:controller_voice_cancel();go_page(HOME_PAGE);break;
 case TouchTarget::QUOTA:go_page(0);break;
 case TouchTarget::CONTROL:go_page(controller_usb_hid_enabled()?HOME_PAGE+1:2);break;
 case TouchTarget::PHONE_HOME:case TouchTarget::PHONE_BACK:{
  if(!controller_usb_hid_enabled()){go_page(2);break;}
  bool ok=controller_usb_phone_key(target==TouchTarget::PHONE_HOME);
  controller_event("action",page.load(),(int)target,1,ok?1:0);break;
 }
 case TouchTarget::UP:case TouchTarget::DOWN:case TouchTarget::LEFT:case TouchTarget::RIGHT:case TouchTarget::CLICK:{
  if(!controller_usb_hid_enabled()){go_page(2);break;}
  bool ok=controller_usb_mouse(target==TouchTarget::LEFT?-24:target==TouchTarget::RIGHT?24:0,
    target==TouchTarget::UP?-24:target==TouchTarget::DOWN?24:0,target==TouchTarget::CLICK);
  controller_event("mouse",page.load(),(int)target,0,ok?1:0);break;
 }
 case TouchTarget::STOP:stop_now();go_page(HOME_PAGE);break;
 case TouchTarget::CONFIRM:{
  taskENTER_CRITICAL(&consent_mux);
  bool same=page==2 && painted_epoch.load()==screen_epoch.load() &&
            painted_hid.load()==controller_usb_hid_enabled() && !screen_failed&&!screen_painting&&!power_locked&&!controller_ota_busy()&&!ble_ota_busy();
  if(now<consent_deadline.load()&&controller::consent_short_tap(consent_visible_at.load(),began,now,same)){
   controller::consent_tap_transition(consent_step.load(),
    [](){consent_step=1;go_page(2);},
    [](){bool enable=!painted_hid.load();controller_usb_request_mode(enable);go_page(enable?HOME_PAGE+1:HOME_PAGE);});
  }
  taskEXIT_CRITICAL(&consent_mux);break;
 }
 default:break;
 }
}
static void input_task(void*){
 controller::TouchGesture gesture;controller::TouchContact contact_state;int touch_page=-1;
 controller::ConsentTapInput touch_confirm,key_confirm,home_confirm;controller::ConsentExitKeyGate side_release;int last_trace_contact=-99;int64_t last_trace_at=0;
 controller::ButtonGesture side_key;controller::ControlButton control_key;controller::GestureDetector swipes;
 controller::DebouncedButton voice_debounce,power_debounce,external_control_debounce;
 controller::PressFeedback voice_press,power_press,external_press;
 unsigned swipe_epoch=0;bool swipe_contact=false;
 bool touch_voicing=false,key_voicing=false;unsigned touch_voice_epoch=0;
 bool updating=false;
 controller::PowerKeyHold power_key;controller::PowerDrain power_drain;bool standby_released=false;controller::StopReleaseGate stop_gate;unsigned seen_stop=stop_sequence.load();
 for(;;){
  controller_ota_input_heartbeat();

  int64_t now=esp_timer_get_time()/1000;
  bool voice_raw=gpio_get_level(GPIO_NUM_0)==0,external_control_raw=false;
#if CONFIG_CONTROLLER_EXTERNAL_KEYS
  voice_raw=voice_raw||gpio_get_level(GPIO_NUM_1)==0;
  external_control_raw=gpio_get_level(GPIO_NUM_2)==0;
#endif
  bool down=voice_debounce.update(voice_raw,now);
  bool power_raw=gpio_get_level(GPIO_NUM_18)==0;
  bool power_down=power_debounce.update(power_raw,now);
  auto power_event=power_key.update(power_raw,now);
  if(power_event==controller::PowerEvent::ARMED){power_locked=true;power_show(1);}
  if(power_event==controller::PowerEvent::OFF||power_event==controller::PowerEvent::RESTART){
   power_locked=true;stop_now();
   power_drain.request(power_event==controller::PowerEvent::OFF?controller::PowerRequest::OFF:controller::PowerRequest::RESTART,now);
  }
  if(power_standby.load()){
   if(!power_down&&!power_raw)standby_released=true;
   if(standby_released&&power_down){gpio_set_level(GPIO_NUM_17,1);esp_restart();}
  }else{
   auto phase=ota_guard_get_phase();
   auto action=power_drain.update(phase==OTA_GUARD_IDLE,phase==OTA_GUARD_COMMIT,now);
   if(action==controller::PowerDrainAction::WAIT_COMMIT)power_show(3);
   else if(action==controller::PowerDrainAction::WAIT)power_show(2);
   else if(action==controller::PowerDrainAction::FAILED){power_show(5);power_locked=false;controller_usb_write("POWER failed: OTA did not drain; maintenance remains available\r\n");}
   else if(action==controller::PowerDrainAction::ACQUIRE&&ota_guard_acquire(OTA_POWER)){
    // Reservation remains held throughout USB-powered standby: no new OTA can race shutdown.
    auto request=power_drain.pending;power_drain.pending=controller::PowerRequest::NONE;
    if(request==controller::PowerRequest::RESTART){gpio_set_level(GPIO_NUM_17,1);esp_restart();}
    else{power_standby=true;standby_released=false;power_show(4);gpio_set_level(GPIO_NUM_17,0);}
   }
  }
  if(page==2)side_release.on_consent_page();
  bool external_control_down=external_control_debounce.update(external_control_raw,now);
  bool control_down=(power_key.ready&&power_down)||external_control_down;
  bool voice_pressed=voice_press.update(down),power_pressed=power_press.update(power_down),external_pressed=external_press.update(external_control_down);
  if(power_view.load()==5&&(voice_pressed||power_pressed||external_pressed))power_show(0);
  if(voice_pressed||power_pressed||external_pressed)controller_audio_prompt(controller::SpeechPrompt::CLICK);
  if(power_locked.load()){
   gesture.cancel();swipes.reset();side_key=controller::ButtonGesture{};control_key=controller::ControlButton{};
   touch_voicing=key_voicing=false;vTaskDelay(pdMS_TO_TICKS(20));continue;
  }
  int tx=0,ty=0;int contact=controller_touch_read(tx,ty);auto edge=contact_state.update(contact);
  auto target=contact==1?controller::touch_target(page.load(),tx,ty,HOME_PAGE):controller::TouchTarget::NONE;
  if(page==2&&(contact!=last_trace_contact||now-last_trace_at>=250)){
   controller_event("touch",2,100+contact,(tx<<16)|ty,gesture.active?(int)(now-gesture.began):0);
   last_trace_contact=contact;last_trace_at=now;
  }else if(page!=2)last_trace_contact=-99;

  if(edge==controller::TouchEdge::DOWN&&power_view.load()==5)power_show(0);
  if(edge==controller::TouchEdge::DOWN)controller_event("touch_down",page.load(),tx,ty,(int)target);
  if(edge==controller::TouchEdge::UP)controller_event("touch_up",page.load(),(int)(gesture.active?now-gesture.began:0),(int)gesture.target,screen_failed?3:screen_painting?2:0);
  // Stop is acted on at contact-down, including during display refresh and OTA.
  if(page==PAGE_COUNT-1&&contact==1)target=controller::voice_touch_target(tx,ty,controller_voice_stage(),controller_voice_conversing(),dialogue_frame_valid.load());
  if(edge==controller::TouchEdge::DOWN&&target!=controller::TouchTarget::STOP)controller_audio_prompt(controller::SpeechPrompt::CLICK);
  if(edge==controller::TouchEdge::DOWN&&target==controller::TouchTarget::STOP){
   stop_now();go_page(HOME_PAGE);touch_voicing=key_voicing=false;gesture.cancel();swipes.reset();
  }
  if(edge==controller::TouchEdge::DOWN&&target==controller::TouchTarget::FINISH){
   bool accepted=controller_voice_finish();controller_event("voice_finish",page.load(),0,0,accepted?1:0);
   gesture.cancel();swipes.reset();swipe_contact=false;
   vTaskDelay(pdMS_TO_TICKS(20));continue;
  }
  auto control_event=control_key.update(control_down,now);
  bool ota_busy=controller_ota_busy()||ble_ota_busy();
  if(control_event==controller::ControlEvent::STOP){
   stop_now();go_page(HOME_PAGE);touch_voicing=key_voicing=false;gesture.cancel();swipes.reset();
  }else if(control_event==controller::ControlEvent::MUTE){
   controller_audio_toggle_mute();
   if(!ota_busy&&!touch_voicing&&!key_voicing)go_page(HOME_PAGE+6);else controller_ota_changed();
  }else if(control_event==controller::ControlEvent::HOME&&!ota_busy){
   if(page==HOME_PAGE+6){controller_audio_adjust(-20);controller_ota_changed();}
   else{controller_voice_cancel();touch_voicing=key_voicing=false;gesture.cancel();swipes.reset();if(page!=HOME_PAGE)go_page(HOME_PAGE);}
  }
  if(seen_stop!=stop_sequence.load()){
   stop_gate.stop();seen_stop=stop_sequence.load();controller_voice_cancel();
   controller_audio_prompt(controller::SpeechPrompt::STOPPED);
  }
  if(stop_gate.blocked(down,control_down,contact==1)){
   gesture.cancel();swipes.reset();side_key=controller::ButtonGesture{};control_key=controller::ControlButton{};
   touch_voicing=key_voicing=false;vTaskDelay(pdMS_TO_TICKS(20));continue;
  }
  if(ota_busy){
   (void)side_key.update(down,now);
   if(!updating){controller_voice_cancel();touch_voicing=key_voicing=false;}
   updating=true;
   gesture.cancel();swipes.reset();vTaskDelay(pdMS_TO_TICKS(20));continue;
  }
  updating=false;
  if(page==2){
   // Confirmation is a separate two-tap flow; ordinary holds/swipes cannot authorize.
   gesture.cancel();swipes.reset();side_key=controller::ButtonGesture{};
   unsigned current=screen_epoch.load();
   bool ready=!screen_painting&&!screen_failed&&painted_epoch.load()==current&&painted_hid.load()==controller_usb_hid_enabled()&&now<consent_deadline.load();
   auto touch_tap=touch_confirm.update(contact,target==controller::TouchTarget::CONFIRM,ready,current,consent_visible_at.load(),now);
   auto key_tap=key_confirm.update(down?1:0,true,ready,current,consent_visible_at.load(),now);
   auto home_tap=home_confirm.update(contact,target==controller::TouchTarget::HOME,ready,current,consent_visible_at.load(),now);
   // At most one transition per loop, even if touch and BOOT are released together.
   if(home_tap.confirm){touch_action(controller::TouchTarget::HOME,home_tap.began,now);}
   else if(touch_tap.confirm||key_tap.confirm){
    auto tap=touch_tap.confirm?touch_tap:key_tap;
    controller_event("consent_tap",2,consent_step.load(),touch_tap.confirm?1:2,(int)(now-tap.began));
    touch_action(controller::TouchTarget::CONFIRM,tap.began,now);
   }
   if(page==2&&consent_deadline>0&&now>=consent_deadline.load())go_page(HOME_PAGE);
   vTaskDelay(pdMS_TO_TICKS(20));continue;
  }
  // Recording release always wins over long-press/double-tap classification.
  if(touch_voicing){
   auto voice_contact=controller::voice_contact(contact,tx,ty,screen_epoch.load()==touch_voice_epoch);
   if(voice_contact==controller::VoiceContact::SEND){touch_voicing=false;controller_voice_hold(false);gesture.cancel();swipes.reset();}
   else if(voice_contact==controller::VoiceContact::CANCEL){
    controller_voice_cancel();touch_voicing=false;gesture.cancel();swipes.reset();
   }
  }else if(contact<0){if(gesture.active)controller_event("touch",page.load(),200,(int)gesture.target,(int)(now-gesture.began));gesture.cancel();swipes.reset();}
  else{
   auto swipe=controller::Gesture::None;
   if(edge==controller::TouchEdge::DOWN){swipe_epoch=screen_epoch.load();swipe_contact=true;}
   if(!screen_painting&&!screen_failed&&page!=2&&!key_voicing&&swipe_contact&&swipe_epoch==screen_epoch.load())
    swipe=swipes.feed(contact==1,tx,ty,now);
   else {swipes.reset();swipe_contact=false;}
   if(contact==0)swipe_contact=false;
   if(controller::is_navigation_gesture(swipe,gesture.target)){
    gesture.cancel();
    switch(swipe){
    case controller::Gesture::SwipeUp:controller_voice_cancel();go_page(controller::next_page(page.load(),HOME_PAGE));break;
    case controller::Gesture::SwipeDown:controller_voice_cancel();go_page(controller::previous_page(page.load(),HOME_PAGE));break;
    case controller::Gesture::DoubleTap:controller_voice_cancel();go_page(HOME_PAGE);break;
    default:break; // Hold-to-talk starts while held; never start it after release.
    }
   }else if(contact==1){
    if(edge==controller::TouchEdge::DOWN){
     touch_page=page.load();
     if(!screen_failed&&!screen_painting)gesture.begin(screen_epoch.load(),painted_epoch.load(),target,now);
     else if(target!=controller::TouchTarget::NONE)controller_event("touch_reject",page.load(),screen_failed?3:2,(int)target);
    }else if(screen_painting||page!=touch_page||target!=gesture.target){
     if(gesture.active)controller_event("touch",page.load(),screen_painting?202:page!=touch_page?203:201,(int)gesture.target,(int)(now-gesture.began));
     gesture.cancel();
    }
   }else if(edge==controller::TouchEdge::UP){
    auto action=gesture.target;int64_t began=gesture.began;
    if(!screen_failed&&!screen_painting&&gesture.release(screen_epoch.load(),now))touch_action(action,began,now);
   }
  }
  if(!touch_voicing&&!key_voicing&&!ota_busy&&controller::touch_hold_to_record(contact==1,gesture.active,gesture.target==controller::TouchTarget::START,screen_epoch.load()==gesture.epoch,screen_painting,now-gesture.began)){
   gesture.cancel();swipes.reset();swipe_contact=false;touch_voicing=true;
   go_page(PAGE_COUNT-1);touch_voice_epoch=screen_epoch.load();stopped=false;controller_voice_hold(true);
  }
  auto side_event=side_release.admit(down)?side_key.update(down,now):controller::ButtonEvent::NONE;
  switch(side_event){
  case controller::ButtonEvent::NEXT:
   if(page==HOME_PAGE+6){controller_audio_adjust(20);controller_ota_changed();}
   else{controller_voice_cancel();touch_voicing=key_voicing=false;gesture.cancel();swipes.reset();go_page(controller::next_page(page.load(),HOME_PAGE));}
   break;
  case controller::ButtonEvent::HOME:
   controller_voice_cancel();touch_voicing=key_voicing=false;gesture.cancel();swipes.reset();go_page(HOME_PAGE);break;
  case controller::ButtonEvent::VOICE_DOWN:
   // A always means hold-to-talk, regardless of the current page. It never
   // silently confirms HID access or starts a firmware update.
   if(!touch_voicing){key_voicing=true;go_page(PAGE_COUNT-1);stopped=false;controller_voice_hold(true);}
   break;
  case controller::ButtonEvent::VOICE_UP:
   if(key_voicing){key_voicing=false;controller_voice_hold(false);}
   break;
  default:break;
  }
  if(page==2&&consent_deadline>0&&now>=consent_deadline.load())go_page(HOME_PAGE);
  vTaskDelay(pdMS_TO_TICKS(20));
 }
}
static bool usb_proof_command(const char *line){
 if(strncmp(line,"PCUSB ",6))return false;
 char id[33]={},encoded[65]={},domain[192]={};uint8_t nonce[32]={},proof[32]={};
 int op=pc_usb_parse(line,id,nonce);if(!op)return true;
 cJSON *obj=cJSON_CreateObject();if(!obj)return true;
 cJSON_AddStringToObject(obj,"device",DISPLAY_DEVICE_ID);
 cJSON_AddStringToObject(obj,"usbSerial",controller_usb_serial());
 if(op==1){cJSON_AddNumberToObject(obj,"protocol",1);cJSON_AddStringToObject(obj,"version",esp_app_get_description()->version);}
 else if(pc_usb_domain(DISPLAY_DEVICE_ID,controller_usb_serial(),domain,sizeof(domain))>0 && controller_device_sign(domain,nonce,proof)){
  for(unsigned i=0;i<32;i++)snprintf(encoded+2*i,3,"%02x",proof[i]);
  cJSON_AddStringToObject(obj,"proof",encoded);
 }else cJSON_AddStringToObject(obj,"error","signing_failed");
 char *json=cJSON_PrintUnformatted(obj);cJSON_Delete(obj);
 if(json){char output[512];int n=snprintf(output,sizeof(output),"PCUSB %s %s\r\n",id,json);free(json);if(n>0&&n<(int)sizeof(output))controller_usb_write(output);}
 memset(nonce,0,sizeof(nonce));memset(proof,0,sizeof(proof));return true;
}
#if CONTROLLER_USB_MAINTENANCE
static void console_maintenance_command(char *line){
 if(power_locked.load()&&strcmp(line,"REBOOT")&&strcmp(line,"BOOTLOADER")&&strcmp(line,"VERSION")&&strcmp(line,"STATUS")&&strcmp(line,"LOGS")&&strcmp(line,"EVENTS")&&strcmp(line,"SCREEN")&&strcmp(line,"HEAP")&&strcmp(line,"ROUTE")&&strcmp(line,"MAINT DEBUG")&&strcmp(line,"STOP")){
  controller_usb_write("POWER pending/standby: input disabled; use REBOOT to resume\r\n");return;
 }
 if(strcmp(line,"STOP")==0)stop_now();
 else if(strcmp(line,"LOGS")==0)controller_logs_dump();
 else if(strcmp(line,"SCREEN")==0){
  static uint8_t snapshot[5000];bool valid;
  taskENTER_CRITICAL(&consent_mux);valid=panel_frame_valid;if(valid)memcpy(snapshot,panel_frame,5000);taskEXIT_CRITICAL(&consent_mux);
  if(valid){
   controller_usb_write("--- SCREEN BEGIN ---\r\n");
   for(int row=0;row<200;++row){char hex[53];for(int x=0;x<25;++x)snprintf(hex+x*2,3,"%02x",snapshot[row*25+x]);strcpy(hex+50,"\r\n");controller_usb_write(hex);}
   controller_usb_write("--- SCREEN END ---\r\n");
  }else controller_usb_write("SCREEN unavailable: no completed panel refresh\r\n");
 }
 else if(strcmp(line,"EVENTS")==0){static char snapshot[4097];controller_events_snapshot(snapshot,sizeof(snapshot));controller_usb_write(snapshot);}
 else if(strcmp(line,"STORAGE")==0)controller_storage_status();
 else if(strcmp(line,"SDLOGS")==0)controller_storage_dump();
 else if(strcmp(line,"SDEVENTS")==0)controller_storage_events_dump();
 else if(strcmp(line,"WIFI ON")==0){
wifi_start();controller_usb_write("WiFi enabled for this boot\r\n");
 }
 else if(strcmp(line,"WIFI OFF")==0){wifi_enabled=false;wifi_connected=false;online=controller_usb_net_has_ip();if(wifi_initialized){esp_wifi_stop();}controller_usb_write("WiFi disabled\r\n");}
 else if(strcmp(line,"HEAP")==0){char out[180];snprintf(out,sizeof(out),"HEAP internal=%u largest=%u dma=%u dma_largest=%u\r\n",(unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT),(unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT),(unsigned)heap_caps_get_free_size(MALLOC_CAP_DMA),(unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_DMA));controller_usb_write(out);}
 else if(strcmp(line,"AUDIO")==0){char out[120];snprintf(out,sizeof(out),"AUDIO volume=%d muted=%d stage=%d recorded_ms=%u level=%u\r\n",controller_audio_volume(),controller_audio_muted(),controller_voice_stage(),controller_voice_recorded_ms(),controller_voice_level());controller_usb_write(out);}
 else if(strcmp(line,"AUDIO UP")==0){controller_audio_adjust(20);controller_ota_changed();}
 else if(strcmp(line,"AUDIO DOWN")==0){controller_audio_adjust(-20);controller_ota_changed();}
 else if(strcmp(line,"AUDIO MUTE")==0){controller_audio_toggle_mute();controller_ota_changed();}
 else if(strcmp(line,"AUDIO TEST")==0){controller_audio_prompt(controller::SpeechPrompt::TEST);}
 else if(strcmp(line,"AUDIO AUDIT")==0){controller_audio_prompt(controller::SpeechPrompt::AUDIT);}
 else if(strcmp(line,"AUDIO CLICK")==0){controller_audio_prompt(controller::SpeechPrompt::CLICK);}
 else if(strcmp(line,"VOICE PREPARE")==0){stopped=false;go_page(PAGE_COUNT-1);controller_voice_prepare();controller_usb_write("Voice connection check requested\r\n");}
 else if(strcmp(line,"VOICE START")==0){stopped=false;go_page(PAGE_COUNT-1);controller_voice_conversation();controller_usb_write("Continuous voice requested\r\n");}
 else if(strcmp(line,"VOICE DOWN")==0){stopped=false;go_page(PAGE_COUNT-1);controller_voice_hold(true);controller_usb_write("Voice hold requested\r\n");}
 else if(strcmp(line,"VOICE FINISH")==0){controller_usb_write(controller_voice_finish()?"Voice submitted\r\n":"Not recording\r\n");}
 else if(strcmp(line,"VOICE UP")==0){controller_voice_hold(false);controller_usb_write("Voice hold released\r\n");}
 else if(strcmp(line,"MIC TEST")==0){controller_voice_test();controller_usb_write("Microphone diagnostic: one second; samples discarded\r\n");}

#if CONTROLLER_USB_MAINTENANCE
 else if(strcmp(line,"MAINT HID ON")==0){stopped=false;controller_usb_request_mode(true);controller_event("hid",page.load(),99,0,1);controller_usb_write("MAINT HID requested for this boot\r\n");}
 else if(strcmp(line,"MAINT DEBUG")==0){controller_usb_write(controller_usb_maintenance_status());}
 else if(strcmp(line,"MAINT HOME")==0){controller_usb_write(controller_usb_phone_key(true)?"MAINT HOME queued\r\n":"MAINT HOME rejected\r\n");}
 else if(strncmp(line,"MAINT CLICK ",12)==0){int x=0,y=0;char tail;bool parsed=sscanf(line+12,"%d %d %c",&x,&y,&tail)==2;controller::PointerCommand c{controller::PointerKind::click,x,y,0,0,0};controller_usb_write(parsed&&controller_usb_maintenance_pointer(c)?"MAINT CLICK queued\r\n":"MAINT CLICK rejected\r\n");}
 else if(strncmp(line,"MAINT DRAG ",11)==0){int x=0,y=0,x2=0,y2=0,ms=0;char tail;bool parsed=sscanf(line+11,"%d %d %d %d %d %c",&x,&y,&x2,&y2,&ms,&tail)==5;controller::PointerCommand c{controller::PointerKind::drag,x,y,x2,y2,ms};controller_usb_write(parsed&&controller_usb_maintenance_pointer(c)?"MAINT DRAG queued\r\n":"MAINT DRAG rejected\r\n");}
#endif
 else if(strcmp(line,"PAGE")==0)go_page(controller::next_page(page.load(),HOME_PAGE));
 else if(strcmp(line,"SAFE")==0){taskENTER_CRITICAL(&consent_mux);controller_usb_request_mode(false);go_page(0);taskEXIT_CRITICAL(&consent_mux);}
 else if(strcmp(line,"OTA")==0){controller_ota_start();go_page(HOME_PAGE+5);controller_usb_write("OTA requested\r\n");}
 else if(strcmp(line,"VERSION")==0){char out[200];snprintf(out,sizeof(out),"VERSION %s slot=%s ota=%d progress=%d\r\n",esp_app_get_description()->version,esp_ota_get_running_partition()->label,controller_ota_stage(),controller_ota_progress());controller_usb_write(out);}
 else if(strcmp(line,"ROUTE")==0){auto *netif=esp_netif_get_default_netif();char info[128];snprintf(info,sizeof(info),"ROUTE default=%s wifi=%d\r\n",netif?esp_netif_get_ifkey(netif):"none",wifi_connected.load());controller_usb_write(info);}
 else if(strcmp(line,"STATUS")==0){
  uint32_t rx,tx;controller_usb_net_counters(&rx,&tx);
  char status[256];snprintf(status,sizeof(status),"STATUS online=%d wifi=%d wifi_enabled=%d usb=%d hid=%d bluetooth=0 page=%d stopped=%d screen_error=%d psram=%u net=%d rx=%u tx=%u voice=%d time=%lld peer=%08x adb=%d\r\n",
   online.load(),wifi_connected.load(),wifi_enabled.load(),controller_usb_ready(),controller_usb_hid_enabled(),page.load(),stopped.load(),screen_failed.load(),(unsigned)esp_psram_get_size(),controller_usb_net_stage(),(unsigned)rx,(unsigned)tx,controller_voice_stage(),(long long)time(nullptr),(unsigned)controller_usb_net_peer(),controller_adb_stage());
  controller_usb_write(status);
 }else if(strcmp(line,"REBOOT")==0 || strcmp(line,"BOOTLOADER")==0){
  if(power_locked.load()&&ota_guard_get_phase()!=OTA_GUARD_POWER){controller_usb_write("POWER waiting for OTA: reboot deferred; retry after completion\r\n");return;}
  gpio_set_level(GPIO_NUM_17,1);
  controller_usb_request_mode(false);
  controller_usb_prepare_reset(strcmp(line,"BOOTLOADER")==0);
  if(strcmp(line,"BOOTLOADER")==0)REG_SET_BIT(RTC_CNTL_OPTION1_REG,RTC_CNTL_FORCE_DOWNLOAD_BOOT);
  esp_restart();
 }else if(strncmp(line,"WIFI\t",5)==0){
  char *split=strchr(line+5,'\t');
  if(split && split-line-5<=32 && strlen(split+1)<=64){
   *split=0;nvs_handle_t h;
   if(nvs_open("wifi",NVS_READWRITE,&h)==ESP_OK){
    nvs_set_str(h,"ssid",line+5);nvs_set_str(h,"password",split+1);nvs_commit(h);nvs_close(h);
    controller_usb_write("WiFi saved; restarting\r\n");vTaskDelay(pdMS_TO_TICKS(300));esp_restart();
   }
  }
 }else controller_usb_write("Commands: STATUS LOGS PAGE STOP SAFE REBOOT BOOTLOADER WIFI ON/OFF; HID requires local screen confirmation\r\n");
}
#endif
static void console_command(char *line){
 controller::usb_console_dispatch(line,CONTROLLER_USB_MAINTENANCE,
  [](char *proof){usb_proof_command(proof);},
  [](){stop_now();},
  [](char *command){
#if CONTROLLER_USB_MAINTENANCE
   console_maintenance_command(command);
#else
   (void)command;
#endif
  },
  [](){controller_usb_write("USB maintenance command disabled in this build\r\n");});
}
static void console_task(void*){
 char line[256]={};size_t used=0;bool overflow=false;
 for(;;){
  controller_usb_service();
  if(online && !sntp_started){
   esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);esp_sntp_setservername(0,"ntp.aliyun.com");esp_sntp_init();sntp_started=true;
  }
  if(screen_dirty.exchange(false) && screen_task_handle)xTaskNotifyGive(screen_task_handle);
  uint8_t bytes[64];size_t n=controller_usb_read(bytes,sizeof(bytes));
  for(size_t i=0;i<n;++i){
   if(bytes[i]=='\n' || bytes[i]=='\r'){
    if(used && !overflow){line[used]=0;console_command(line);}
    memset(line,0,sizeof(line));used=0;overflow=false;
   }else if(used<sizeof(line)-1)line[used++]=(char)bytes[i];
   else overflow=true;
  }
  vTaskDelay(pdMS_TO_TICKS(20));
 }
}
// User-authorized LAN read-only diagnostics; no tokens, frames or control routes.
static esp_err_t lan_status(httpd_req_t *req){
 char state[384],body[768];controller_diagnostic_state(state,sizeof(state));
 auto *netif=esp_netif_get_default_netif();
 snprintf(body,sizeof(body),"{\"version\":\"%s\",\"defaultRoute\":\"%s\",\"wifiConnected\":%s,\"internalFree\":%u,\"internalLargest\":%u,\"state\":%s}",
 esp_app_get_description()->version,netif?esp_netif_get_ifkey(netif):"none",wifi_connected?"true":"false",
 (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT),(unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT),state);
 httpd_resp_set_type(req,"application/json");httpd_resp_set_hdr(req,"Cache-Control","no-store");
 return httpd_resp_sendstr(req,body);
}
static esp_err_t lan_trace(httpd_req_t *req){
 char *buffer=(char*)heap_caps_malloc(8193,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
 if(!buffer){httpd_resp_set_status(req,"503 Service Unavailable");return httpd_resp_sendstr(req,"diagnostic buffer unavailable");}
 size_t n=0;
 if(!strcmp(req->uri,"/logs"))n=controller_logs_snapshot(buffer,8193);
 else if(!strcmp(req->uri,"/events"))n=controller_events_snapshot(buffer,8193);
 else n=controller_storage_tail(!strcmp(req->uri,"/tf/events"),buffer,8193);
 httpd_resp_set_type(req,"text/plain; charset=utf-8");httpd_resp_set_hdr(req,"Cache-Control","no-store");
 esp_err_t result=httpd_resp_send(req,buffer,n);free(buffer);return result;
}
static void lan_diagnostics_start(){
 static httpd_handle_t server=nullptr;if(server)return;
 httpd_config_t config=HTTPD_DEFAULT_CONFIG();config.server_port=8088;config.stack_size=4096;
 config.max_open_sockets=2;config.max_uri_handlers=6;config.lru_purge_enable=true;
 config.recv_wait_timeout=2;config.send_wait_timeout=2;
 esp_err_t err=httpd_start(&server,&config);
 if(err!=ESP_OK){server=nullptr;ESP_LOGE(TAG,"LAN diagnostics start failed: %s",esp_err_to_name(err));return;}
 httpd_uri_t status={};status.uri="/status";status.method=HTTP_GET;status.handler=lan_status;
 err=httpd_register_uri_handler(server,&status);
 ESP_LOGI(TAG,"LAN read-only diagnostics port=8088 status=%s",esp_err_to_name(err));
 const char *paths[]={"/logs","/events","/tf/events","/tf/diag"};
 for(const char *path:paths){httpd_uri_t trace={};trace.uri=path;trace.method=HTTP_GET;trace.handler=lan_trace;httpd_register_uri_handler(server,&trace);}

}

extern "C" void app_main(){
 // Assert the battery latch before NVS, networking or other slow initialization.
 gpio_config_t power={};power.pin_bit_mask=(1ULL<<6)|(1ULL<<42)|(1ULL<<17);power.mode=GPIO_MODE_OUTPUT;
 ESP_ERROR_CHECK(gpio_config(&power));gpio_set_level(GPIO_NUM_6,0);gpio_set_level(GPIO_NUM_42,1);gpio_set_level(GPIO_NUM_17,1);

 controller_logs_start();controller_event("boot",HOME_PAGE);
 ESP_LOGI(TAG,"Boot reset_reason=%d; HID=OFF WiFi=LAN-DIAGNOSTIC Bluetooth=BLE-OTA",esp_reset_reason());
 ESP_ERROR_CHECK(nvs_flash_init());
 ESP_ERROR_CHECK(esp_netif_init());ESP_ERROR_CHECK(esp_event_loop_create_default());
 // User-authorized LAN diagnostic: reserve WiFi memory before USB/audio/BLE.
 wifi_start();
 gpio_config_t button={};button.pin_bit_mask=(1ULL<<0)|(1ULL<<18);
#if CONFIG_CONTROLLER_EXTERNAL_KEYS
 button.pin_bit_mask|=(1ULL<<1)|(1ULL<<2);
#endif
button.mode=GPIO_MODE_INPUT;button.pull_up_en=GPIO_PULLUP_ENABLE;ESP_ERROR_CHECK(gpio_config(&button));
 controller_touch_init();
 controller_usb_start();
#if CONFIG_CONTROLLER_USB_LOCAL && CONFIG_CONTROLLER_ADB_MAINTENANCE
 controller_adb_init();
#endif
 controller_voice_init();
 controller_storage_start();
 // BLE OTA 先起：板子即使没 Wi-Fi/USB，也能靠手机蓝牙推固件。
 { int rc=ble_ota_start(); if(rc!=0)ESP_LOGE(TAG,"BLE OTA start failed rc=%d",rc); }
 xTaskCreate(screen_task,"screen",12288,nullptr,3,&screen_task_handle);
 xTaskCreate(telemetry_task,"telemetry",12288,nullptr,2,nullptr);
 xTaskCreate(input_task,"button",3072,nullptr,5,nullptr);
 xTaskCreate(console_task,"console",4096,nullptr,2,nullptr);
 lan_diagnostics_start();
 controller_ota_health_start();
 if(controller::wifi_on_boot())wifi_start();
 ESP_LOGI(TAG,"Epaper controller boot: PSRAM=%u; no automatic HID actions",(unsigned)esp_psram_get_size());
}
