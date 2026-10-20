#include "usb.h"
#include <atomic>
#include <stdio.h>
#include <string.h>
#include "tinyusb.h"
#include "tinyusb_default_config.h"
#include "tinyusb_cdc_acm.h"
#include "class/hid/hid_device.h"
#include "esp_mac.h"
#include "esp_private/usb_phy.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mode_consent.h"

static std::atomic<bool> enabled(controller::hid_on_boot()), requested(false), release_pending(false);
static const uint8_t report_descriptor[]={
 TUD_HID_REPORT_DESC_KEYBOARD(HID_REPORT_ID(1)),
 TUD_HID_REPORT_DESC_MOUSE(HID_REPORT_ID(2))
};
static char serial_number[13];
static const char* strings[]={"\x09\x04","Personal Controller","Epaper Phone Controller",serial_number,"Console","Keyboard and Mouse"};
static const uint8_t safe_descriptor[]={
 TUD_CONFIG_DESCRIPTOR(1,2,0,TUD_CONFIG_DESC_LEN+TUD_CDC_DESC_LEN,0,100),
 TUD_CDC_DESCRIPTOR(0,4,0x81,8,0x02,0x82,64)
};
static const uint8_t hid_descriptor[]={
 TUD_CONFIG_DESCRIPTOR(1,3,0,TUD_CONFIG_DESC_LEN+TUD_CDC_DESC_LEN+TUD_HID_DESC_LEN,0,100),
 TUD_CDC_DESCRIPTOR(0,4,0x81,8,0x02,0x82,64),
 TUD_HID_DESCRIPTOR(2,5,HID_ITF_PROTOCOL_NONE,sizeof(report_descriptor),0x83,16,10)
};
static tusb_desc_device_t device_descriptor;
extern "C" uint8_t const *tud_hid_descriptor_report_cb(uint8_t){return report_descriptor;}
extern "C" uint16_t tud_hid_get_report_cb(uint8_t,uint8_t,hid_report_type_t,uint8_t*,uint16_t){return 0;}
extern "C" void tud_hid_set_report_cb(uint8_t,uint8_t,hid_report_type_t,const uint8_t*,uint16_t){}
bool controller_usb_ready(){return tud_mounted();}
bool controller_usb_hid_enabled(){return enabled.load();}
void controller_release(){release_pending=true;}
void controller_usb_request_mode(bool value){requested=value;}
static void release_reports(){
 if(!enabled)return;
 uint8_t keys[6]={};
 for(int report=1;report<=2;++report){
  for(int wait=0;wait<5&&!tud_hid_ready();++wait)vTaskDelay(pdMS_TO_TICKS(10));
  if(tud_hid_ready()){
   if(report==1)tud_hid_keyboard_report(1,0,keys);
   else tud_hid_mouse_report(2,0,0,0,0,0);
  }
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
 device_descriptor.idProduct=hid?0x4005:0x4001;
 device_descriptor.bcdDevice=0x0200;
 device_descriptor.iManufacturer=1;device_descriptor.iProduct=2;device_descriptor.iSerialNumber=3;
 device_descriptor.bNumConfigurations=1;
 tinyusb_config_t cfg=TINYUSB_DEFAULT_CONFIG();
 cfg.descriptor.device=&device_descriptor;
 cfg.descriptor.full_speed_config=hid?hid_descriptor:safe_descriptor;
 cfg.descriptor.string=strings;
 cfg.descriptor.string_count=sizeof(strings)/sizeof(strings[0]);
 ESP_ERROR_CHECK(tinyusb_driver_install(&cfg));
 tinyusb_config_cdcacm_t cdc={};
 ESP_ERROR_CHECK(tinyusb_cdcacm_init(&cdc));
 enabled=hid;
}
void controller_usb_start(){
 uint8_t mac[6];ESP_ERROR_CHECK(esp_read_mac(mac,ESP_MAC_BASE));
 snprintf(serial_number,sizeof(serial_number),"%02X%02X%02X%02X%02X%02X",mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
 requested=false;enabled=false;install(false);
}
// Only the console task services USB changes and accesses CDC. No stdio VFS is
// torn down under another task, and no mode permission survives any reboot.
void controller_usb_service(){
 if(release_pending.exchange(false))release_reports();
 bool target=requested.load();
 if(target==enabled.load())return;
 release_reports();
 tud_disconnect();
 vTaskDelay(pdMS_TO_TICKS(250));
 ESP_ERROR_CHECK(tinyusb_driver_uninstall());
 ESP_ERROR_CHECK(tinyusb_cdcacm_deinit(TINYUSB_CDC_ACM_0));
 enabled=false;
 vTaskDelay(pdMS_TO_TICKS(100));
 // Recheck revocation before and after installation.
 install(target && requested.load());
 if(enabled && !requested.load()){
  tud_disconnect();
  ESP_ERROR_CHECK(tinyusb_driver_uninstall());
  ESP_ERROR_CHECK(tinyusb_cdcacm_deinit(TINYUSB_CDC_ACM_0));
  enabled=false;install(false);
 }
}
size_t controller_usb_read(uint8_t *data,size_t size){
 size_t count=0;
 if(tud_mounted())tinyusb_cdcacm_read(TINYUSB_CDC_ACM_0,data,size,&count);
 return count;
}
void controller_usb_prepare_reset(bool download){
 requested=false;release_reports();tud_disconnect();
 vTaskDelay(pdMS_TO_TICKS(300));
 if(download){
  // Give the shared internal PHY back to the hardware download controller.
  ESP_ERROR_CHECK(tinyusb_driver_uninstall());
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
