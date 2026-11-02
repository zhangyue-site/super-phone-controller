#include "usb.h"
#include "ota_ble.h"
#include "relay.h"
#include "touch_descriptor.h"
#include <string.h>
#include <stdio.h>
#include <stdatomic.h>
#include "tinyusb.h"
#include "tinyusb_default_config.h"
#include "tinyusb_cdc_acm.h"
#include "class/hid/hid_device.h"
#include "esp_mac.h"
#include "esp_private/usb_phy.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#if CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG_ENABLED
#error "TinyUSB must not share its PHY with the console"
#endif
static atomic_bool armed,started,installed;
static atomic_uint completed[2];
static SemaphoreHandle_t input_mutex;
static char serial[13];
static const uint8_t reports[]={TUD_HID_REPORT_DESC_MOUSE(HID_REPORT_ID(1)),TUD_HID_REPORT_DESC_CONSUMER(HID_REPORT_ID(2)),TUD_HID_REPORT_DESC_KEYBOARD(HID_REPORT_ID(3))};
static const uint8_t config[]={
 TUD_CONFIG_DESCRIPTOR(1,4,0,TUD_CONFIG_DESC_LEN+TUD_CDC_DESC_LEN+2*TUD_HID_DESC_LEN,0,100),
 TUD_CDC_DESCRIPTOR(0,4,0x81,8,0x02,0x82,64),
 TUD_HID_DESCRIPTOR(2,5,HID_ITF_PROTOCOL_NONE,sizeof(reports),0x83,16,5),
 TUD_HID_DESCRIPTOR(3,5,HID_ITF_PROTOCOL_NONE,sizeof(amoled_touch_descriptor),0x84,16,5)};
static const char *strings[]={"\x09\x04","Personal Controller","AMOLED Plugin Controller",serial,"Plugin Console","Phone Input"};
static const tusb_desc_device_t device={.bLength=sizeof(tusb_desc_device_t),.bDescriptorType=TUSB_DESC_DEVICE,.bcdUSB=0x0200,.bDeviceClass=TUSB_CLASS_MISC,.bDeviceSubClass=MISC_SUBCLASS_COMMON,.bDeviceProtocol=MISC_PROTOCOL_IAD,.bMaxPacketSize0=CFG_TUD_ENDPOINT0_SIZE,.idVendor=0x303a,.idProduct=0x4005,.bcdDevice=0x0200,.iManufacturer=1,.iProduct=2,.iSerialNumber=3,.bNumConfigurations=1};
uint8_t const *tud_hid_descriptor_report_cb(uint8_t instance){return instance==1?amoled_touch_descriptor:reports;}
uint16_t tud_hid_get_report_cb(uint8_t instance,uint8_t id,hid_report_type_t type,uint8_t *b,uint16_t len){if(instance==1&&id==5&&type==HID_REPORT_TYPE_FEATURE&&len){b[0]=2;return 1;}return 0;}
void tud_hid_set_report_cb(uint8_t instance,uint8_t id,hid_report_type_t type,uint8_t const *b,uint16_t len){}
void tud_hid_report_complete_cb(uint8_t instance,uint8_t const *report,uint16_t len){if(instance<2)atomic_fetch_add(&completed[instance],1);}
static void event(tinyusb_event_t *e,void *arg){if(e->id==TINYUSB_EVENT_DETACHED){armed=false;amoled_relay_usb_detached();}}
esp_err_t amoled_usb_start(void){
 input_mutex=xSemaphoreCreateMutex();if(!input_mutex)return ESP_ERR_NO_MEM;
 uint8_t mac[6];esp_err_t result=esp_read_mac(mac,ESP_MAC_BASE);if(result!=ESP_OK)return result;
 snprintf(serial,sizeof(serial),"%02X%02X%02X%02X%02X%02X",mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
 tinyusb_config_t cfg=TINYUSB_DEFAULT_CONFIG();cfg.event_cb=event;cfg.descriptor.device=&device;cfg.descriptor.full_speed_config=config;cfg.descriptor.string=strings;cfg.descriptor.string_count=6;
 result=tinyusb_driver_install(&cfg);if(result!=ESP_OK)return result;installed=true;tinyusb_config_cdcacm_t cdc={0};result=tinyusb_cdcacm_init(&cdc);started=result==ESP_OK;return result;
}
bool amoled_usb_ready(void){return started&&tud_mounted();}
bool amoled_usb_armed(void){return armed&&amoled_usb_ready();}
static bool permitted(bool release,bool (*live)(uint32_t),uint32_t epoch){return amoled_usb_ready()&&(release||(!amoled_ota_busy()&&armed&&(!live||live(epoch))));}
// One input owner at a time. Acknowledgement waits for the actual USB completion.
static bool send_report(uint8_t instance,uint8_t id,const void *data,uint16_t length,bool release,bool (*live)(uint32_t),uint32_t epoch){
 int64_t deadline=esp_timer_get_time()+300000;
 while(!tud_hid_n_ready(instance)){if(!permitted(release,live,epoch)||esp_timer_get_time()>=deadline)return false;vTaskDelay(pdMS_TO_TICKS(2));}
 if(!permitted(release,live,epoch))return false;
 unsigned before=atomic_load(&completed[instance]);if(!tud_hid_n_report(instance,id,data,length))return false;
 while(atomic_load(&completed[instance])==before){if(!amoled_usb_ready()||esp_timer_get_time()>=deadline)return false;vTaskDelay(pdMS_TO_TICKS(2));}
 return permitted(release,live,epoch);
}
static bool touch(uint8_t down,uint16_t x,uint16_t y,bool release,bool (*live)(uint32_t),uint32_t epoch){uint8_t data[]={down,0,x&255,x>>8,y&255,y>>8,1};return send_report(1,4,data,sizeof(data),release,live,epoch);}
static void release_all(void){uint8_t zero[8]={0};send_report(0,1,zero,5,true,NULL,0);send_report(0,2,zero,2,true,NULL,0);send_report(0,3,zero,8,true,NULL,0);touch(0,0,0,true,NULL,0);}
bool amoled_usb_reserve_ota(bool (*reserve)(void)){
 if(!input_mutex||xSemaphoreTake(input_mutex,0)!=pdTRUE)return false;
 bool ok=!armed&&reserve();xSemaphoreGive(input_mutex);return ok;
}
void amoled_usb_gate(bool enable){
 if(enable){
  if(!input_mutex||xSemaphoreTake(input_mutex,0)!=pdTRUE)return;
  armed=!amoled_ota_busy()&&amoled_usb_ready();xSemaphoreGive(input_mutex);return;
 }
 armed=false;
 if(input_mutex&&xSemaphoreTake(input_mutex,0)==pdTRUE){if(amoled_usb_ready())release_all();xSemaphoreGive(input_mutex);}
}

static bool key_report(uint8_t modifier,uint8_t usage,bool (*live)(uint32_t),uint32_t epoch){uint8_t data[8]={modifier,0,usage,0,0,0,0,0};bool ok=send_report(0,3,data,8,false,live,epoch);memset(data,0,8);bool released=send_report(0,3,data,8,true,NULL,0);return ok&&released&&permitted(false,live,epoch);}
static bool consumer(uint16_t usage,bool (*live)(uint32_t),uint32_t epoch){uint8_t data[2]={usage&255,usage>>8};bool ok=send_report(0,2,data,2,false,live,epoch);vTaskDelay(pdMS_TO_TICKS(20));data[0]=data[1]=0;bool released=send_report(0,2,data,2,true,NULL,0);return ok&&released&&permitted(false,live,epoch);}
static bool ascii_key(uint8_t c,uint8_t *modifier,uint8_t *usage){
 *modifier=0;
 if(c>='a'&&c<='z'){*usage=c-'a'+4;return true;}
 if(c>='A'&&c<='Z'){*modifier=2;*usage=c-'A'+4;return true;}
 if(c>='1'&&c<='9'){*usage=c-'1'+0x1e;return true;}if(c=='0'){*usage=0x27;return true;}
 const char plain[]=" -=[]\\;'/.,`";const uint8_t codes[]={0x2c,0x2d,0x2e,0x2f,0x30,0x31,0x33,0x34,0x38,0x37,0x36,0x35};
 const char shifted[]="!@#$%^&*()_+{}|:\"?><~";const uint8_t shift_codes[]={0x1e,0x1f,0x20,0x21,0x22,0x23,0x24,0x25,0x26,0x27,0x2d,0x2e,0x2f,0x30,0x31,0x33,0x34,0x38,0x37,0x36,0x35};
 for(size_t i=0;i<sizeof(plain)-1;i++)if(c==plain[i]){*usage=codes[i];return true;}
 for(size_t i=0;i<sizeof(shifted)-1;i++)if(c==shifted[i]){*modifier=2;*usage=shift_codes[i];return true;}
 return false;
}
bool amoled_usb_execute(uint8_t op,const uint16_t a[5],bool (*live)(uint32_t),uint32_t epoch){
 if(!input_mutex||!permitted(false,live,epoch)||xSemaphoreTake(input_mutex,pdMS_TO_TICKS(100))!=pdTRUE)return false;
 bool ok=false;
 if(op==1||op==2||op==9||op==10)ok=consumer(op==1?0x223:op==2?0x224:op==9?0xe9:0xea,live,epoch);
 else if(op==8||op==13)ok=key_report(op==13?a[0]:0,op==13?a[1]:a[0],live,epoch);
 else if(op==14){
  ok=true;for(unsigned i=0;i<a[0]&&ok;i++){uint8_t ch=(uint8_t)(a[1+i/2]>>(8*(i%2))),modifier,usage;ok=ascii_key(ch,&modifier,&usage)&&key_report(modifier,usage,live,epoch);}
 }else if(op==3||op==4){
  uint16_t x=a[0],y=a[1];ok=touch(0,x,y,false,live,epoch)&&touch(1,x,y,false,live,epoch);
  if(op==3){vTaskDelay(pdMS_TO_TICKS(40));ok=ok&&permitted(false,live,epoch);}
  else{
   int64_t begin=esp_timer_get_time();while(ok){int64_t elapsed=(esp_timer_get_time()-begin)/1000;if(elapsed>a[4])elapsed=a[4];x=a[0]+((int32_t)a[2]-a[0])*elapsed/a[4];y=a[1]+((int32_t)a[3]-a[1])*elapsed/a[4];ok=touch(1,x,y,false,live,epoch);if(elapsed>=a[4])break;vTaskDelay(pdMS_TO_TICKS(10));}
  }
  bool released=touch(0,x,y,true,NULL,0);ok=ok&&released&&permitted(false,live,epoch);
 }
 if(!permitted(false,live,epoch)){release_all();}
 xSemaphoreGive(input_mutex);return ok;
}
bool amoled_usb_consumer(unsigned usage){if(!input_mutex||!amoled_usb_armed()||xSemaphoreTake(input_mutex,pdMS_TO_TICKS(50))!=pdTRUE)return false;bool ok=consumer(usage,NULL,0);xSemaphoreGive(input_mutex);return ok;}
bool amoled_usb_mouse(int dx,int dy,bool click){
 if(!input_mutex||!amoled_usb_armed()||xSemaphoreTake(input_mutex,pdMS_TO_TICKS(50))!=pdTRUE)return false;
 int8_t data[5]={click?1:0,dx,dy,0,0};bool ok=send_report(0,1,data,5,false,NULL,0);if(click){data[0]=0;ok=send_report(0,1,data,5,true,NULL,0)&&ok;}xSemaphoreGive(input_mutex);return ok;
}
size_t amoled_usb_read(char *out,size_t size){size_t n=0;if(!started)return 0;tinyusb_cdcacm_read(TINYUSB_CDC_ACM_0,(uint8_t*)out,size,&n);return n;}
size_t amoled_usb_write_bytes(const void *data,size_t total){const uint8_t *s=data;size_t sent=0;for(int retry=0;sent<total&&retry<3000&&tud_mounted();retry++){sent+=tinyusb_cdcacm_write_queue(TINYUSB_CDC_ACM_0,s+sent,total-sent);tinyusb_cdcacm_write_flush(TINYUSB_CDC_ACM_0,0);if(sent<total)vTaskDelay(pdMS_TO_TICKS(2));}return sent;}
void amoled_usb_write(const char *s){amoled_usb_write_bytes(s,strlen(s));}
const char *amoled_usb_serial(void){return serial;}

esp_err_t amoled_usb_enter_bootloader(void){
 amoled_relay_cancel();amoled_usb_gate(false);
 if(installed){
  tud_disconnect();vTaskDelay(pdMS_TO_TICKS(300));
  esp_err_t e=tinyusb_driver_uninstall();if(e!=ESP_OK)return e;
  installed=false;
  if(started){tinyusb_cdcacm_deinit(TINYUSB_CDC_ACM_0);started=false;}
 }
 // The OTG stack and hardware download controller share one internal PHY.
 // Give it back before forcing ROM mode; otherwise the serial port can vanish.
 usb_phy_config_t config={0};config.controller=USB_PHY_CTRL_SERIAL_JTAG;config.target=USB_PHY_TARGET_INT;
 usb_phy_handle_t download_phy;esp_err_t e=usb_new_phy(&config,&download_phy);if(e!=ESP_OK)return e;
 REG_SET_BIT(RTC_CNTL_OPTION1_REG,RTC_CNTL_FORCE_DOWNLOAD_BOOT);
 esp_restart();return ESP_FAIL;
}
