#include "usb.h"
#include "tinyusb.h"
#include "tinyusb_default_config.h"
#include "tinyusb_cdc_acm.h"
#include "tinyusb_console.h"
#include "class/hid/hid_device.h"

static const uint8_t report_descriptor[]={
 TUD_HID_REPORT_DESC_KEYBOARD(HID_REPORT_ID(1)),
 TUD_HID_REPORT_DESC_MOUSE(HID_REPORT_ID(2))
};
static const char* strings[]={"\x09\x04","Personal Controller","Epaper Phone Controller","EPAPER-CONTROLLER-01","Console","Keyboard and Mouse"};
static const uint8_t config_descriptor[]={
 TUD_CONFIG_DESCRIPTOR(1,3,0,TUD_CONFIG_DESC_LEN+TUD_CDC_DESC_LEN+TUD_HID_DESC_LEN,0,100),
 TUD_CDC_DESCRIPTOR(0,4,0x81,8,0x02,0x82,64),
 TUD_HID_DESCRIPTOR(2,5,HID_ITF_PROTOCOL_NONE,sizeof(report_descriptor),0x83,16,10)
};
extern "C" uint8_t const *tud_hid_descriptor_report_cb(uint8_t instance){return report_descriptor;}
extern "C" uint16_t tud_hid_get_report_cb(uint8_t,uint8_t,hid_report_type_t,uint8_t*,uint16_t){return 0;}
extern "C" void tud_hid_set_report_cb(uint8_t,uint8_t,hid_report_type_t,const uint8_t*,uint16_t){}
bool controller_usb_ready(){return tud_mounted();}
void controller_release(){
 if(tud_hid_ready())tud_hid_mouse_report(2,0,0,0,0,0);
 // No key-down is generated in this dashboard firmware.
}
void controller_usb_start(){
 tinyusb_config_t cfg=TINYUSB_DEFAULT_CONFIG();
 cfg.descriptor.full_speed_config=config_descriptor;
 cfg.descriptor.string=strings;
 cfg.descriptor.string_count=sizeof(strings)/sizeof(strings[0]);
 ESP_ERROR_CHECK(tinyusb_driver_install(&cfg));
 tinyusb_config_cdcacm_t cdc={};
 ESP_ERROR_CHECK(tinyusb_cdcacm_init(&cdc));
 ESP_ERROR_CHECK(tinyusb_console_init(TINYUSB_CDC_ACM_0));
}
