#include "usb.h"
#include "usb_console_policy.h"
#include "keyboard_policy.h"
#include "usb_endpoint_budget.h"
#include "absolute_touch_report.h"
#include "android_touch_descriptor.h"
#include "diagnostics.h"
#include "usb_network.h"
#include <atomic>
#include <stdio.h>
#include <string.h>
#include "tinyusb.h"
#include "tinyusb_default_config.h"
#include "tinyusb_cdc_acm.h"
#include "class/hid/hid_device.h"
#include "esp_mac.h"
#include "esp_log.h"
#include "esp_private/usb_phy.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mode_consent.h"
#include "freertos/semphr.h"

static std::atomic<bool> enabled(controller::hid_on_boot()), requested(false), release_pending(false);
static const uint8_t report_descriptor[]={
 TUD_HID_REPORT_DESC_KEYBOARD(HID_REPORT_ID(1)),
 TUD_HID_REPORT_DESC_MOUSE(HID_REPORT_ID(2)),
 TUD_HID_REPORT_DESC_CONSUMER(HID_REPORT_ID(3)),

};
static char serial_number[13],network_mac[13];
static std::atomic<int> mouse_command(0);
static std::atomic<bool> mouse_down(false),consumer_down(false);
static std::atomic<uint8_t> key_code(0),key_modifier(0);
static std::atomic<int> key_state(0);
static bool (*key_live)(unsigned)=nullptr;
static unsigned key_sequence=0;
static int64_t key_deadline=0;
static SemaphoreHandle_t pointer_mutex=nullptr;
static controller::PointerSequence pointer_sequence;
static std::atomic<bool> pointer_active(false);
static bool (*pointer_live)(unsigned)=nullptr;
static unsigned pointer_voice_sequence=0;
static bool send_absolute_pointer(const controller::PointerReport& report){auto bytes=controller::absolute_touch_report(report.buttons,report.x,report.y);return tud_hid_n_report(1,4,bytes.data(),bytes.size());}
// All absolute reports and state transitions occur in the USB service task.
static std::atomic<bool> maintenance_pointer(false);
static bool pointer_service(){
 if(!pointer_mutex||xSemaphoreTake(pointer_mutex,0)!=pdTRUE)return pointer_active.load();
 if(pointer_active){
  if(!enabled||!tud_mounted())pointer_sequence.detached();
  else {
   if(!requested||!pointer_live||!pointer_live(pointer_voice_sequence))pointer_sequence.cancel();
   controller::PointerReport report;
   uint32_t now=xTaskGetTickCount()*portTICK_PERIOD_MS;
   if(tud_hid_n_ready(1)&&pointer_sequence.next(now,report)&&
      send_absolute_pointer(report))pointer_sequence.submitted(now);
  }
  pointer_active=pointer_sequence.active();
 }
 bool active=pointer_active.load();if(!active&&maintenance_pointer.exchange(false))controller_event("mouse",-1,90,0,pointer_sequence.success()?1:0);xSemaphoreGive(pointer_mutex);return active;
}
// 0 idle, 1 pending, 2 press submitted, 3 released, -1 failed/cancelled.
static std::atomic<int> ai_home_state(0);
static std::atomic<uint16_t> ai_key_usage(0x0223);
static std::atomic_flag ai_home_busy=ATOMIC_FLAG_INIT;
bool controller_usb_ai_key(bool home,bool (*live)(unsigned),unsigned sequence){
 if(ai_home_busy.test_and_set())return false;
 bool ok=false;
 if(enabled&&requested&&tud_mounted()&&!pointer_active&&!mouse_command.load()&&!mouse_down&&!consumer_down&&live(sequence)){
  int state=ai_home_state.load();
  if(state==0||state==3||state==-1){
   ai_key_usage=home?0x0223:0x0224;ai_home_state=1;
   for(int i=0;i<300;++i){
    if(!live(sequence)||!enabled||!requested||!tud_mounted())break;
    state=ai_home_state.load();
    if(state==3){ok=true;break;}
    if(state==-1)break;
    vTaskDelay(pdMS_TO_TICKS(10));
   }
   // A pending command cannot execute after timeout/cancellation. An already
   // submitted press is released by the USB service or local STOP.
   int pending=1;ai_home_state.compare_exchange_strong(pending,-1);
  }
 }
 ai_home_busy.clear();return ok&&live(sequence);
}
bool controller_usb_ai_home(bool (*live)(unsigned),unsigned sequence){return controller_usb_ai_key(true,live,sequence);}
bool controller_usb_consumer(uint16_t usage,bool (*live)(unsigned),unsigned sequence){
 if(ai_home_busy.test_and_set())return false;
 bool ok=false;
 if(enabled&&requested&&tud_mounted()&&!pointer_active&&!mouse_command.load()&&!mouse_down&&!consumer_down&&key_state.load()==0&&live(sequence)){
  int state=ai_home_state.load();
  if(state==0||state==3||state==-1){
   ai_key_usage=usage;ai_home_state=1;
   for(int i=0;i<300&&live(sequence)&&enabled&&requested&&tud_mounted();++i){
    state=ai_home_state.load();
    if(state==3){ok=true;break;}
    if(state==-1)break;
    vTaskDelay(pdMS_TO_TICKS(10));
   }
   int pending=1;ai_home_state.compare_exchange_strong(pending,-1);
  }
 }
 ai_home_busy.clear();return ok&&live(sequence);
}
// Completion is reported only after both press and release transfers complete.
extern "C" void tud_hid_report_complete_cb(uint8_t instance,const uint8_t* report,uint16_t length){
 int state=key_state.load();
 int next=controller::keyboard_completed(state,instance,report,length,key_modifier.load(),key_code.load());
 if(next!=state)key_state.compare_exchange_strong(state,next);
}
static bool keyboard_step(uint8_t modifier,uint8_t code,bool (*live)(unsigned),unsigned sequence,int64_t deadline){
 if(!enabled||!requested||!tud_mounted()||!live(sequence)||!controller::keyboard_before_deadline(esp_timer_get_time(),deadline))return false;
 int idle=key_state.load();if(idle==3||idle==-1)key_state=0;
 if(key_state.load()!=0)return false;
 key_live=live;key_sequence=sequence;key_deadline=deadline;key_code=code;key_modifier=modifier;key_state=1;bool ok=false;
 for(int i=0;i<300&&live(sequence)&&enabled&&requested&&tud_mounted()&&controller::keyboard_before_deadline(esp_timer_get_time(),deadline);++i){
  int state=key_state.load();if(state==3){ok=true;break;}if(state==-1)break;
  vTaskDelay(pdMS_TO_TICKS(10));
 }
 ok=ok&&controller::keyboard_before_deadline(esp_timer_get_time(),deadline);
 if(ok)key_state=0;
 else {int pending=1;if(!key_state.compare_exchange_strong(pending,0))release_pending=true;}
 return ok&&live(sequence);
}
bool controller_usb_keyboard(uint8_t modifier,uint8_t code,bool (*live)(unsigned),unsigned sequence){
 if(!controller::keyboard_usage(code)||ai_home_busy.test_and_set())return false;
 bool ok=keyboard_step(modifier,code,live,sequence,esp_timer_get_time()+3000000);ai_home_busy.clear();return ok;
}
bool controller_usb_key(uint8_t code,bool (*live)(unsigned),unsigned sequence){
 if(code<4||code>231||ai_home_busy.test_and_set())return false;
 bool ok=keyboard_step(0,code,live,sequence,esp_timer_get_time()+3000000);ai_home_busy.clear();return ok;
}
bool controller_usb_ascii(const uint8_t *text,size_t length,bool (*live)(unsigned),unsigned sequence){
 if(!text||length<1||length>8)return false;
 for(size_t i=0;i<length;++i)if(text[i]<0x20||text[i]>0x7e)return false;
 if(ai_home_busy.test_and_set())return false;
 bool ok=true;const int64_t deadline=esp_timer_get_time()+7500000;
 for(size_t i=0;i<length&&ok;++i){uint8_t modifier,usage;ok=controller::ascii_key(text[i],modifier,usage)&&keyboard_step(modifier,usage,live,sequence,deadline);}
 ai_home_busy.clear();return ok&&live(sequence);
}
bool controller_usb_phone_key(bool home){
 if(ai_home_busy.test_and_set())return false;
 bool ok=false;int empty=0;
 if(enabled&&requested&&tud_mounted()&&!pointer_active)ok=mouse_command.compare_exchange_strong(empty,home?6:7);
 ai_home_busy.clear();return ok;
}
bool controller_usb_mouse(int dx,int dy,bool click){
 if(ai_home_busy.test_and_set())return false;
 bool ok=false;
 if(enabled&&requested&&tud_mounted()&&!pointer_active&&dx>=-64&&dx<=64&&dy>=-64&&dy<=64){
  int value=click?1:dx<0?2:dx>0?3:dy<0?4:dy>0?5:0;int empty=0;
  ok=value&&mouse_command.compare_exchange_strong(empty,value);
 }
 ai_home_busy.clear();return ok;
}
bool controller_usb_ai_pointer(const controller::PointerCommand& command,bool (*live)(unsigned),unsigned sequence){
 if(!live||!pointer_mutex||ai_home_busy.test_and_set())return false;
 bool started=false,ok=false;
 if(xSemaphoreTake(pointer_mutex,pdMS_TO_TICKS(100))==pdTRUE){
  if(enabled&&requested&&tud_mounted()&&live(sequence)&&!pointer_active&&
     !mouse_command.load()&&!mouse_down&&!consumer_down&&ai_home_state.load()!=1&&ai_home_state.load()!=2){
   bool drag=command.kind==controller::PointerKind::drag;
   if(controller::valid_pointer(command,drag,drag,drag)){
    pointer_live=live;pointer_voice_sequence=sequence;started=pointer_sequence.begin(command);pointer_active=started;
   }
  }
  xSemaphoreGive(pointer_mutex);
 }
 if(started){
  for(int i=0;i<350;++i){
   if(xSemaphoreTake(pointer_mutex,pdMS_TO_TICKS(20))==pdTRUE){
    if(!live(sequence)||!enabled||!requested||i==349)pointer_sequence.cancel();
    bool active=pointer_sequence.active();ok=pointer_sequence.success();
    // Cancel may require release: retain ownership until USB service submits it.
    if(active)pointer_active=true;
    xSemaphoreGive(pointer_mutex);
    if(!active||!live(sequence)||i==349)break;
   }
   vTaskDelay(pdMS_TO_TICKS(10));
  }
  // Even if every timed lock failed, timeout must revoke queued work.
  xSemaphoreTake(pointer_mutex,portMAX_DELAY);
  if(pointer_sequence.active()){pointer_sequence.cancel();ok=false;pointer_active=pointer_sequence.active();}
  xSemaphoreGive(pointer_mutex);
 }
 ai_home_busy.clear();return ok&&live(sequence);
}
static std::atomic<bool> switching(false);
static std::atomic<bool> download_request(false),saw_boot_reset(false);
void controller_usb_prepare_reset(bool download);
static void enter_download_mode(){
 download_request.store(false);saw_boot_reset.store(false);requested=false;
 controller_usb_prepare_reset(true);
 REG_SET_BIT(RTC_CNTL_OPTION1_REG,RTC_CNTL_FORCE_DOWNLOAD_BOOT);
 esp_restart();
}
static void cdc_line_state(int,cdcacm_event_t *event){
 if(!event||event->type!=CDC_EVENT_LINE_STATE_CHANGED)return;
 bool seen=saw_boot_reset.load();
 bool download=controller::usb_download_line_state(CONTROLLER_USB_MAINTENANCE,switching.load(),event->line_state_changed_data.dtr,event->line_state_changed_data.rts,seen);
 saw_boot_reset.store(seen);if(download)download_request.store(true);
}
#if CONFIG_TINYUSB_NET_MODE_NCM
#define NETWORK_INTERFACES 2
#define NETWORK_LENGTH TUD_CDC_NCM_DESC_LEN
#define NETWORK_DESCRIPTOR TUD_CDC_NCM_DESCRIPTOR(2,5,6,0x83,64,0x04,0x84,64,1514),
#define MOUSE_ENDPOINT 0x85
#else
#define NETWORK_INTERFACES 0
#define NETWORK_LENGTH 0
#define NETWORK_DESCRIPTOR
#define MOUSE_ENDPOINT 0x83
#endif
extern void controller_usb_disconnected();
static std::atomic<bool> network_profile(true);
static void usb_event(tinyusb_event_t *event,void*){
 if(event->id==TINYUSB_EVENT_ATTACHED){
  if(gpio_get_level(GPIO_NUM_0)==0)download_request.store(true);
  if(network_profile)controller_usb_net_link(true);
 }
 else if(event->id==TINYUSB_EVENT_DETACHED){
  controller_usb_net_link(false);
  if(!switching)controller_usb_disconnected();
 }
}
static const char* strings[]={"\x09\x04","Personal Controller","Epaper Phone Controller",serial_number,"Console","USB Network",network_mac,"Keyboard and Mouse"};
static const uint8_t safe_descriptor[]={
 TUD_CONFIG_DESCRIPTOR(1,2+NETWORK_INTERFACES,0,TUD_CONFIG_DESC_LEN+TUD_CDC_DESC_LEN+NETWORK_LENGTH,0,100),
 TUD_CDC_DESCRIPTOR(0,4,0x81,8,0x02,0x82,64),
 NETWORK_DESCRIPTOR
};
// HID mode fits EP0 + CDC notify/data + legacy HID + direct touch in five IN FIFOs.
// NCM remains in the safe/maintenance profile; Pixel currently uses Wi-Fi for cloud and ADB acceptance.
static constexpr uint8_t hid_descriptor[]={
 TUD_CONFIG_DESCRIPTOR(1,4,0,TUD_CONFIG_DESC_LEN+TUD_CDC_DESC_LEN+2*TUD_HID_DESC_LEN,0,100),
 TUD_CDC_DESCRIPTOR(0,4,0x81,8,0x02,0x82,64),
 TUD_HID_DESCRIPTOR(2,7,HID_ITF_PROTOCOL_NONE,sizeof(report_descriptor),0x83,16,10),
 TUD_HID_DESCRIPTOR(3,7,HID_ITF_PROTOCOL_NONE,sizeof(controller::android_touch_descriptor),0x84,16,10)
};
static_assert(controller::in_endpoint_count(hid_descriptor,sizeof(hid_descriptor))+1<=5,"ESP32-S3 IN FIFO budget includes EP0");
static tusb_desc_device_t device_descriptor;
extern "C" uint8_t const *tud_hid_descriptor_report_cb(uint8_t instance){return instance==1?controller::android_touch_descriptor:report_descriptor;}
extern "C" uint16_t tud_hid_get_report_cb(uint8_t instance,uint8_t id,hid_report_type_t type,uint8_t* buffer,uint16_t length){if(instance==1&&id==5&&type==HID_REPORT_TYPE_FEATURE&&length){buffer[0]=2;return 1;}return 0;}
extern "C" void tud_hid_set_report_cb(uint8_t,uint8_t,hid_report_type_t,const uint8_t*,uint16_t){}
bool controller_usb_ready(){return tud_mounted();}
bool controller_usb_hid_enabled(){return enabled.load();}
void controller_release(){release_pending=true;}
static std::atomic<unsigned> maintenance_generation(0);
void controller_usb_request_mode(bool value){if(!value){maintenance_generation.fetch_add(1);}requested=value;}
static void release_reports(){
 mouse_command=0;mouse_down=false;consumer_down=false;
 if(pointer_mutex&&xSemaphoreTake(pointer_mutex,pdMS_TO_TICKS(100))==pdTRUE){
  if(pointer_active)pointer_sequence.cancel();
  xSemaphoreGive(pointer_mutex);
 }
 // Retry absolute releases in the normal service if the endpoint is busy.
 pointer_service();
 if(ai_home_state.load()==1||ai_home_state.load()==2)ai_home_state=-1;
 if(key_state.load())key_state=-1;
 if(!enabled)return;
 uint8_t keys[6]={};
 for(int report=1;report<=3;++report){
  for(int wait=0;wait<5&&!tud_hid_ready();++wait)vTaskDelay(pdMS_TO_TICKS(10));
  if(tud_hid_ready()){
   if(report==1){if(!tud_hid_keyboard_report(1,0,keys))release_pending=true;}
   else if(report==2)tud_hid_mouse_report(2,0,0,0,0,0);
   else {uint16_t usage=0;tud_hid_report(3,&usage,sizeof(usage));}
  }else if(report==1&&tud_mounted())release_pending=true;
 }
}
static void install(bool hid){
 device_descriptor={};
 device_descriptor.bLength=sizeof(device_descriptor);
 device_descriptor.bDescriptorType=TUSB_DESC_DEVICE;
 device_descriptor.bcdUSB=0x0200;
 device_descriptor.bDeviceClass=TUSB_CLASS_MISC;
 device_descriptor.bDeviceSubClass=MISC_SUBCLASS_COMMON;
 device_descriptor.bDeviceProtocol=MISC_PROTOCOL_IAD;
 device_descriptor.bMaxPacketSize0=CFG_TUD_ENDPOINT0_SIZE;
 device_descriptor.idVendor=0x303a;
 // Espressif's default PID bitmap: CDC=bit0, HID=bit2.
 device_descriptor.idProduct=(hid?0x4005:0x4001)|(NETWORK_INTERFACES?0x40:0);
 device_descriptor.bcdDevice=0x0200;
 device_descriptor.iManufacturer=1;device_descriptor.iProduct=2;device_descriptor.iSerialNumber=3;
 device_descriptor.bNumConfigurations=1;
 tinyusb_config_t cfg=TINYUSB_DEFAULT_CONFIG();
 cfg.event_cb=usb_event;
 cfg.descriptor.device=&device_descriptor;
 cfg.descriptor.full_speed_config=hid?hid_descriptor:safe_descriptor;
 cfg.descriptor.string=strings;
 cfg.descriptor.string_count=sizeof(strings)/sizeof(strings[0]);
 network_profile=!hid;
 ESP_ERROR_CHECK(tinyusb_driver_install(&cfg));
 tinyusb_config_cdcacm_t cdc={};
 ESP_ERROR_CHECK(tinyusb_cdcacm_init(&cdc));
 ESP_ERROR_CHECK(tinyusb_cdcacm_register_callback(TINYUSB_CDC_ACM_0,CDC_EVENT_LINE_STATE_CHANGED,cdc_line_state));
 if(!hid)controller_usb_net_attach();
 enabled=hid;
}
void controller_usb_start(){
 pointer_mutex=xSemaphoreCreateMutex();configASSERT(pointer_mutex);
 uint8_t mac[6];ESP_ERROR_CHECK(esp_read_mac(mac,ESP_MAC_BASE));
 snprintf(serial_number,sizeof(serial_number),"%02X%02X%02X%02X%02X%02X",mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
 controller_usb_net_init();controller_usb_net_mac_string(network_mac);
 requested=false;enabled=false;install(false);
}
// Only the console task services USB changes and accesses CDC. No stdio VFS is
// torn down under another task, and no mode permission survives any reboot.
void controller_usb_service(){
 controller_usb_net_service();
 if(download_request.load())enter_download_mode();
 if(release_pending.exchange(false))release_reports();
 bool absolute_busy=pointer_service();
 bool target=requested.load();
 if(target==enabled.load()){
  if(enabled&&tud_mounted()&&tud_hid_ready()&&xSemaphoreTake(pointer_mutex,0)==pdTRUE){
   if(key_state.load()==2){uint8_t up[6]={};key_state=5;if(!tud_hid_keyboard_report(1,0,up))key_state=2;}
   else if(key_state.load()==1&&!consumer_down&&!mouse_down){if(!key_live||!key_live(key_sequence)||!requested||!controller::keyboard_before_deadline(esp_timer_get_time(),key_deadline)){key_state=-1;xSemaphoreGive(pointer_mutex);return;}uint8_t down[6]={key_code.load()};key_state=4;if(!tud_hid_keyboard_report(1,key_modifier.load(),down))key_state=1;}
   else if(consumer_down){uint16_t usage=0;bool released=tud_hid_report(3,&usage,sizeof(usage));if(released){consumer_down=false;if(ai_home_state.load()==2)ai_home_state=3;}}
   else if(mouse_down){tud_hid_mouse_report(2,0,0,0,0,0);mouse_down=false;}
   else if(!absolute_busy&&!pointer_active){
    int pending=1;
    if(requested.load()&&ai_home_state.compare_exchange_strong(pending,2)){
     uint16_t usage=ai_key_usage.load();
     bool sent=tud_hid_report(3,&usage,sizeof(usage));
     consumer_down=sent;if(!sent)ai_home_state=-1;
     controller_event("ai_home",-1,0,0,sent?1:0);
     xSemaphoreGive(pointer_mutex);return;
    }
    int command=mouse_command.exchange(0);
    if(command&&requested.load()){
     bool sent;
     if(command>=6){uint16_t usage=command==6?0x0223:0x0224;sent=tud_hid_report(3,&usage,sizeof(usage));consumer_down=sent;}
     else sent=tud_hid_mouse_report(2,command==1?1:0,command==2?-24:command==3?24:0,command==4?-24:command==5?24:0,0,0);
     mouse_down=sent&&command==1;controller_event("mouse",-1,command,0,sent?1:0);
    }
   }
   xSemaphoreGive(pointer_mutex);
  }
  return;
 }
 release_reports();
 switching=true;controller_usb_net_begin_detach();
 tud_disconnect();
 vTaskDelay(pdMS_TO_TICKS(250));
 ESP_ERROR_CHECK(tinyusb_driver_uninstall());
 controller_usb_net_detach();
 ESP_ERROR_CHECK(tinyusb_cdcacm_deinit(TINYUSB_CDC_ACM_0));
 enabled=false;
 vTaskDelay(pdMS_TO_TICKS(100));
 // Recheck revocation before and after installation.
 install(target && requested.load());
 if(enabled && !requested.load()){
  controller_usb_net_begin_detach();tud_disconnect();
  ESP_ERROR_CHECK(tinyusb_driver_uninstall());
  controller_usb_net_detach();
  ESP_ERROR_CHECK(tinyusb_cdcacm_deinit(TINYUSB_CDC_ACM_0));
  enabled=false;install(false);
 }
 switching=false;controller_event("hid",-1,enabled.load(),0,1);
}
size_t controller_usb_read(uint8_t *data,size_t size){
 size_t count=0;
 if(tud_mounted())tinyusb_cdcacm_read(TINYUSB_CDC_ACM_0,data,size,&count);
 return count;
}
void controller_usb_prepare_reset(bool download){
 requested=false;release_reports();switching=true;controller_usb_net_begin_detach();tud_disconnect();
 vTaskDelay(pdMS_TO_TICKS(300));
 if(download){
  // Give the shared internal PHY back to the hardware download controller.
  ESP_ERROR_CHECK(tinyusb_driver_uninstall());
  controller_usb_net_detach();
  ESP_ERROR_CHECK(tinyusb_cdcacm_deinit(TINYUSB_CDC_ACM_0));
  usb_phy_config_t cfg={};cfg.controller=USB_PHY_CTRL_SERIAL_JTAG;cfg.target=USB_PHY_TARGET_INT;
  usb_phy_handle_t phy;
  ESP_ERROR_CHECK(usb_new_phy(&cfg,&phy));
 }
}
void controller_usb_write(const char *text){
 if(!tud_mounted())return;
 size_t total=strlen(text),sent=0;
 for(int retry=0;sent<total&&retry<100&&tud_mounted();++retry){
  sent+=tinyusb_cdcacm_write_queue(TINYUSB_CDC_ACM_0,(const uint8_t*)text+sent,total-sent);
  tinyusb_cdcacm_write_flush(TINYUSB_CDC_ACM_0,0);
  if(sent<total)vTaskDelay(pdMS_TO_TICKS(10));
 }
}

// Private diagnostic USB maintenance, compiled only in this authorized build.
#if CONTROLLER_USB_MAINTENANCE
static bool maintenance_live(unsigned seq){return seq==maintenance_generation.load()&&requested.load()&&enabled.load()&&tud_mounted();}
bool controller_usb_maintenance_pointer(const controller::PointerCommand& command){
 if(!controller::valid_pointer(command,command.kind==controller::PointerKind::drag,command.kind==controller::PointerKind::drag,command.kind==controller::PointerKind::drag)||!requested||!enabled||!tud_mounted()||ai_home_busy.test_and_set())return false;
 bool ok=false;
 if(xSemaphoreTake(pointer_mutex,pdMS_TO_TICKS(50))==pdTRUE){
  if(!pointer_active&&!mouse_command.load()&&!mouse_down&&!consumer_down&&ai_home_state.load()!=1&&ai_home_state.load()!=2){
   pointer_live=maintenance_live;pointer_voice_sequence=maintenance_generation.load();ok=pointer_sequence.begin(command);pointer_active=ok;maintenance_pointer=ok;
  }
  xSemaphoreGive(pointer_mutex);
 }
 ai_home_busy.clear();return ok;
}
#endif

#if CONTROLLER_USB_MAINTENANCE
const char* controller_usb_maintenance_status(){static char out[240];snprintf(out,sizeof(out),"USBDBG mounted=%d ready=%d suspended=%d hidready=%d touchready=%d enabled=%d requested=%d queue=%d home=%d pointer=%d\r\n",tud_mounted(),tud_ready(),tud_suspended(),tud_hid_ready(),tud_hid_n_ready(1),enabled.load(),requested.load(),mouse_command.load(),ai_home_state.load(),pointer_active.load());return out;}
#endif

const char *controller_usb_serial(void){return serial_number;}
