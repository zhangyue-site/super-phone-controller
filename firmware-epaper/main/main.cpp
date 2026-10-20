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
#include "device_config.h"
#include "boot_screen.h"
#include "mode_screens.h"
#include "mode_consent.h"
#include "diagnostics.h"
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

static const char *TAG="controller";
static std::atomic<bool> online(false), stopped(false), stop_pending(false);
static std::atomic<int> page(0);
static std::atomic<int64_t> consent_visible_at(0);
static std::atomic<unsigned> screen_epoch(1), painted_epoch(0);
static std::atomic<bool> painted_hid(false), screen_failed(false), screen_dirty(false);
static TaskHandle_t screen_task_handle;
static portMUX_TYPE consent_mux=portMUX_INITIALIZER_UNLOCKED;
static void go_page(int target){
 taskENTER_CRITICAL(&consent_mux);
 consent_visible_at=0;screen_epoch.fetch_add(1);page=target;
 taskEXIT_CRITICAL(&consent_mux);
 screen_dirty=true;
}

static char ssid[33],password[65];
static int network_slot=0,retries=0;
static std::atomic<bool> wifi_enabled(false);
static bool wifi_initialized=false;

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
static void wifi_event(void*,esp_event_base_t base,int32_t id,void*){
 if(!wifi_enabled){online=false;return;}
 if(base==IP_EVENT && id==IP_EVENT_STA_GOT_IP){online=true;retries=0;ESP_LOGI(TAG,"WiFi connected");if(screen_task_handle)xTaskNotifyGive(screen_task_handle);}
 else if(base==WIFI_EVENT && id==WIFI_EVENT_STA_DISCONNECTED){online=false; if(++retries>=3){retries=0;network_slot=(network_slot+1)%10;connect_saved();}else esp_wifi_connect();}
 else if(base==WIFI_EVENT && id==WIFI_EVENT_STA_START)connect_saved();
}
static void wifi_start(){
 if(wifi_enabled.exchange(true))return;
 if(wifi_initialized){esp_wifi_start();esp_sntp_init();return;}
 ESP_ERROR_CHECK(esp_netif_init());ESP_ERROR_CHECK(esp_event_loop_create_default());
 esp_netif_create_default_wifi_sta();wifi_init_config_t init=WIFI_INIT_CONFIG_DEFAULT();
 ESP_ERROR_CHECK(esp_wifi_init(&init));
 ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
 ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT,ESP_EVENT_ANY_ID,wifi_event,nullptr));
 ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT,IP_EVENT_STA_GOT_IP,wifi_event,nullptr));
 ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));ESP_ERROR_CHECK(esp_wifi_start());
 wifi_initialized=true;
 esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);esp_sntp_setservername(0,"ntp.aliyun.com");esp_sntp_init();
}
static bool request(const char *path,uint8_t *out){
 char url[256],auth[128];snprintf(url,sizeof(url),"%s%s",DISPLAY_ENDPOINT,path);
 snprintf(auth,sizeof(auth),"Bearer %s",DISPLAY_TOKEN);
 esp_http_client_config_t cfg={};cfg.url=url;cfg.timeout_ms=8000;
 cfg.common_name="erweima.zhangyue.site";
 cfg.crt_bundle_attach=esp_crt_bundle_attach;cfg.buffer_size=2048;cfg.disable_auto_redirect=true;
 esp_http_client_handle_t client=esp_http_client_init(&cfg);if(!client)return false;
 esp_http_client_set_header(client,"Authorization",auth);
 esp_http_client_set_header(client,"Host","erweima.zhangyue.site");
 if(!out)esp_http_client_set_method(client,HTTP_METHOD_POST);
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
 if(!ok)ESP_LOGW(TAG,"Display request failed status=%d bytes=%d error=%s",status,total,esp_err_to_name(err));
 return ok;
}
static bool paint(epaper_driver_display &display,const uint8_t *frame,bool full){
 for(int y=0;y<200;y++)for(int x=0;x<200;x++)
  display.EPD_DrawColorPixel(x,y,frame[y*25+x/8]&(0x80>>(x%8))?255:0);
 if(full){display.EPD_Init();display.EPD_DisplayPartBaseImage();display.EPD_Init_Partial();}
 else display.EPD_DisplayPart();
 return display.healthy();
}
static void screen_task(void*){
 custom_lcd_spi_t pins={11,10,9,8,13,12,SPI3_HOST,5000};
 epaper_driver_display display(200,200,pins);
 uint8_t frame[5000],previous[5000];memset(previous,0,sizeof(previous));
 int refreshes=0;unsigned previous_epoch=0;
 for(;;){
  const unsigned epoch=screen_epoch.load();
  const int current_page=page.load();
  const bool hid=controller_usb_hid_enabled();
  bool success=false;
  if(online && stop_pending.exchange(false) && !request("/stop",nullptr))stop_pending=true;
  if(current_page==2){
   memcpy(frame,hid?mode_enabled_screen:mode_disabled_screen,5000);
  }else{
   if(online){
    char path[48];snprintf(path,sizeof(path),"/screen.bin?page=%d",current_page);
    success=request(path,frame);
   }
   if(!success)memcpy(frame,boot_screen,5000);
  }
  if(epoch!=screen_epoch.load() || current_page!=page.load())continue;
  if(memcmp(frame,previous,5000) || previous_epoch!=epoch){
   if(!paint(display,frame,refreshes++%20==0)){
    consent_visible_at=0;screen_failed=true;
    ESP_LOGE(TAG,"Screen disabled after driver fault; USB recovery remains available");
    vTaskSuspend(nullptr);
   }
   memcpy(previous,frame,5000);previous_epoch=epoch;
   taskENTER_CRITICAL(&consent_mux);
   if(current_page==2 && epoch==screen_epoch.load() && page==2){
    painted_hid=hid;painted_epoch=epoch;
    consent_visible_at=esp_timer_get_time()/1000;
   }
   taskEXIT_CRITICAL(&consent_mux);
   ESP_LOGI(TAG,"Screen updated page=%d",current_page);
  }
  ulTaskNotifyTake(pdTRUE,pdMS_TO_TICKS(15000));
 }
}
static void stop_now(){
 taskENTER_CRITICAL(&consent_mux);
 stopped=true;stop_pending=true;controller_release();controller_usb_request_mode(false);go_page(1);
 taskEXIT_CRITICAL(&consent_mux);
 if(screen_task_handle)xTaskNotifyGive(screen_task_handle);
 ESP_LOGI(TAG,"Local stop latched; no actuator enabled");
}
static void input_task(void*){
 bool held=false,long_sent=false;int64_t began=0;
 bool power_held=false,power_done=false;int64_t power_began=0;
 for(;;){
  bool down=gpio_get_level(GPIO_NUM_0)==0;
  int64_t now=esp_timer_get_time()/1000;
  if(down&&!held){held=true;long_sent=false;began=now;}
  if(down&&held&&!long_sent&&page!=2&&now-began>=1200){long_sent=true;stop_now();}
  if(!down&&held){
   held=false;
   if(!long_sent && page==2 && now-began>=2000){
    taskENTER_CRITICAL(&consent_mux);
    bool same=page==2 && painted_epoch.load()==screen_epoch.load() &&
              painted_hid.load()==controller_usb_hid_enabled() && !screen_failed;
    if(controller::can_confirm(consent_visible_at.load(),began,now,same)){
     controller_usb_request_mode(!painted_hid.load());go_page(0);
    }
    taskEXIT_CRITICAL(&consent_mux);
   }else if(!long_sent&&now-began>=50){go_page((page.load()+1)%3);}
  }
  if(page==2 && consent_visible_at>0 && now-consent_visible_at.load()>=15000)go_page(0);
  bool power_down=gpio_get_level(GPIO_NUM_18)==0;
  if(power_down&&!power_held){power_held=true;power_done=false;power_began=now;}
  if(!power_down)power_held=false;
  if(power_down&&power_held&&!power_done&&now-power_began>=1500){
   power_done=true;stop_now();
   ESP_LOGI(TAG,"PWR long press: disabling battery power latch; USB may still supply power");
   gpio_set_level(GPIO_NUM_17,0);
  }
  vTaskDelay(pdMS_TO_TICKS(20));
 }
}
static void console_command(char *line){
 if(strcmp(line,"STOP")==0)stop_now();
 else if(strcmp(line,"LOGS")==0)controller_logs_dump();
 else if(strcmp(line,"WIFI ON")==0){wifi_start();controller_usb_write("WiFi enabled for this boot\r\n");}
 else if(strcmp(line,"WIFI OFF")==0){wifi_enabled=false;online=false;if(wifi_initialized){esp_sntp_stop();esp_wifi_stop();}controller_usb_write("WiFi disabled\r\n");}
 else if(strcmp(line,"PAGE")==0)go_page((page.load()+1)%3);
 else if(strcmp(line,"SAFE")==0){taskENTER_CRITICAL(&consent_mux);controller_usb_request_mode(false);go_page(0);taskEXIT_CRITICAL(&consent_mux);}
 else if(strcmp(line,"STATUS")==0){
  char status[200];snprintf(status,sizeof(status),"STATUS wifi=%d wifi_enabled=%d usb=%d hid=%d bluetooth=0 page=%d stopped=%d screen_error=%d psram=%u\r\n",
   online.load(),wifi_enabled.load(),controller_usb_ready(),controller_usb_hid_enabled(),page.load(),stopped.load(),screen_failed.load(),(unsigned)esp_psram_get_size());
  controller_usb_write(status);
 }else if(strcmp(line,"REBOOT")==0 || strcmp(line,"BOOTLOADER")==0){
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
static void console_task(void*){
 char line[256]={};size_t used=0;bool overflow=false;
 for(;;){
  controller_usb_service();
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
extern "C" void app_main(){
 controller_logs_start();
 ESP_LOGI(TAG,"Boot reset_reason=%d; HID=OFF WiFi=OFF Bluetooth=OFF",esp_reset_reason());
 ESP_ERROR_CHECK(nvs_flash_init());
 gpio_config_t power={};power.pin_bit_mask=(1ULL<<6)|(1ULL<<42)|(1ULL<<17);power.mode=GPIO_MODE_OUTPUT;
 ESP_ERROR_CHECK(gpio_config(&power));gpio_set_level(GPIO_NUM_6,0);gpio_set_level(GPIO_NUM_42,1);gpio_set_level(GPIO_NUM_17,1);
 gpio_config_t button={};button.pin_bit_mask=(1ULL<<0)|(1ULL<<18);button.mode=GPIO_MODE_INPUT;button.pull_up_en=GPIO_PULLUP_ENABLE;ESP_ERROR_CHECK(gpio_config(&button));
 controller_usb_start();
 xTaskCreate(screen_task,"screen",24576,nullptr,3,&screen_task_handle);
 xTaskCreate(input_task,"button",3072,nullptr,5,nullptr);
 xTaskCreate(console_task,"console",4096,nullptr,2,nullptr);
 if(controller::wifi_on_boot())wifi_start();
 ESP_LOGI(TAG,"Epaper controller boot: PSRAM=%u; no automatic HID actions",(unsigned)esp_psram_get_size());
}
