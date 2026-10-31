#include "usb.h"
#include <string.h>
#include <stdio.h>
#include "tinyusb.h"
#include "tinyusb_default_config.h"
#include "tinyusb_cdc_acm.h"
#include "class/hid/hid_device.h"
#include "esp_mac.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
static bool armed;
static char serial[13];
static const uint8_t reports[]={TUD_HID_REPORT_DESC_MOUSE(HID_REPORT_ID(1)),TUD_HID_REPORT_DESC_CONSUMER(HID_REPORT_ID(2))};
static const uint8_t config[]={
 TUD_CONFIG_DESCRIPTOR(1,3,0,TUD_CONFIG_DESC_LEN+TUD_CDC_DESC_LEN+TUD_HID_DESC_LEN,0,100),
 TUD_CDC_DESCRIPTOR(0,4,0x81,8,0x02,0x82,64),
 TUD_HID_DESCRIPTOR(2,5,HID_ITF_PROTOCOL_NONE,sizeof(reports),0x83,16,10)};
static const char *strings[]={"\x09\x04","Personal Controller","AMOLED Plugin Controller",serial,"Plugin Console","Manual Input"};
static const tusb_desc_device_t device={.bLength=sizeof(tusb_desc_device_t),.bDescriptorType=TUSB_DESC_DEVICE,.bcdUSB=0x0200,.bDeviceClass=TUSB_CLASS_MISC,.bDeviceSubClass=MISC_SUBCLASS_COMMON,.bDeviceProtocol=MISC_PROTOCOL_IAD,.bMaxPacketSize0=CFG_TUD_ENDPOINT0_SIZE,.idVendor=0x303a,.idProduct=0x4005,.bcdDevice=0x0100,.iManufacturer=1,.iProduct=2,.iSerialNumber=3,.bNumConfigurations=1};
uint8_t const *tud_hid_descriptor_report_cb(uint8_t instance){return reports;}
uint16_t tud_hid_get_report_cb(uint8_t instance,uint8_t id,hid_report_type_t type,uint8_t *b,uint16_t len){return 0;}
void tud_hid_set_report_cb(uint8_t instance,uint8_t id,hid_report_type_t type,uint8_t const *b,uint16_t len){}
static void event(tinyusb_event_t *e,void *arg){if(e->id==TINYUSB_EVENT_DETACHED)armed=false;}
void usb_start(void){
 uint8_t mac[6];ESP_ERROR_CHECK(esp_read_mac(mac,ESP_MAC_BASE));
 snprintf(serial,sizeof(serial),"%02X%02X%02X%02X%02X%02X",mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
 tinyusb_config_t cfg=TINYUSB_DEFAULT_CONFIG();cfg.event_cb=event;cfg.descriptor.device=&device;cfg.descriptor.full_speed_config=config;cfg.descriptor.string=strings;cfg.descriptor.string_count=6;
 ESP_ERROR_CHECK(tinyusb_driver_install(&cfg));tinyusb_config_cdcacm_t cdc={0};ESP_ERROR_CHECK(tinyusb_cdcacm_init(&cdc));
}
bool usb_ready(void){return tud_mounted();}
bool usb_armed(void){return armed&&usb_ready();}
static bool ready(void){for(int i=0;i<12&&!tud_hid_ready();i++)vTaskDelay(pdMS_TO_TICKS(5));return tud_hid_ready();}
void usb_gate(bool enable){armed=enable&&usb_ready();if(!armed&&ready()){tud_hid_mouse_report(1,0,0,0,0,0);if(ready()){uint16_t u=0;tud_hid_report(2,&u,2);}}}
bool usb_consumer(unsigned usage){if(!usb_armed()||!ready())return false;uint16_t u=usage;if(!tud_hid_report(2,&u,2))return false;vTaskDelay(pdMS_TO_TICKS(20));u=0;return ready()&&tud_hid_report(2,&u,2);}
bool usb_mouse(int dx,int dy,bool click){if(!usb_armed()||!ready())return false;if(!tud_hid_mouse_report(1,click?1:0,dx,dy,0,0))return false;if(!click)return true;vTaskDelay(pdMS_TO_TICKS(20));return ready()&&tud_hid_mouse_report(1,0,0,0,0,0);}
size_t usb_read(char *out,size_t size){size_t n=0;tinyusb_cdcacm_read(TINYUSB_CDC_ACM_0,(uint8_t*)out,size,&n);return n;}
void usb_write(const char *s){tinyusb_cdcacm_write_queue(TINYUSB_CDC_ACM_0,(const uint8_t*)s,strlen(s));tinyusb_cdcacm_write_flush(TINYUSB_CDC_ACM_0,20);}
