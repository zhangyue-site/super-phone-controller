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

static const char *TAG="controller";
static std::atomic<bool> online(false), stopped(false), stop_pending(false);
static std::atomic<int> page(0);
static TaskHandle_t screen_task_handle;
static char ssid[33],password[65];
static int network_slot=0,retries=0;

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
 if(base==IP_EVENT && id==IP_EVENT_STA_GOT_IP){online=true;retries=0;ESP_LOGI(TAG,"WiFi connected");if(screen_task_handle)xTaskNotifyGive(screen_task_handle);}
 else if(base==WIFI_EVENT && id==WIFI_EVENT_STA_DISCONNECTED){online=false; if(++retries>=3){retries=0;network_slot=(network_slot+1)%10;connect_saved();}else esp_wifi_connect();}
 else if(base==WIFI_EVENT && id==WIFI_EVENT_STA_START)connect_saved();
}
static void wifi_start(){
 ESP_ERROR_CHECK(esp_netif_init());ESP_ERROR_CHECK(esp_event_loop_create_default());
 esp_netif_create_default_wifi_sta();wifi_init_config_t init=WIFI_INIT_CONFIG_DEFAULT();
 ESP_ERROR_CHECK(esp_wifi_init(&init));
 ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
 ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT,ESP_EVENT_ANY_ID,wifi_event,nullptr));
 ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT,IP_EVENT_STA_GOT_IP,wifi_event,nullptr));
 ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));ESP_ERROR_CHECK(esp_wifi_start());
 esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);esp_sntp_setservername(0,"ntp.aliyun.com");esp_sntp_init();
}
static bool request(const char *path,uint8_t *out){
 char url[256],auth[128];snprintf(url,sizeof(url),"%s%s",DISPLAY_ENDPOINT,path);
 snprintf(auth,sizeof(auth),"Bearer %s",DISPLAY_TOKEN);
 esp_http_client_config_t cfg={};cfg.url=url;cfg.timeout_ms=8000;
 cfg.common_name="controller.example.invalid";
 cfg.crt_bundle_attach=esp_crt_bundle_attach;cfg.buffer_size=2048;cfg.disable_auto_redirect=true;
 esp_http_client_handle_t client=esp_http_client_init(&cfg);if(!client)return false;
 esp_http_client_set_header(client,"Authorization",auth);
 esp_http_client_set_header(client,"Host","controller.example.invalid");
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
static void paint(epaper_driver_display &display,const uint8_t *frame,bool full){
 for(int y=0;y<200;y++)for(int x=0;x<200;x++)
  display.EPD_DrawColorPixel(x,y,frame[y*25+x/8]&(0x80>>(x%8))?255:0);
 if(full){display.EPD_Init();display.EPD_DisplayPartBaseImage();display.EPD_Init_Partial();}
 else display.EPD_DisplayPart();
}
static void screen_task(void*){
 custom_lcd_spi_t pins={11,10,9,8,13,12,SPI3_HOST,5000};
 epaper_driver_display display(200,200,pins);
 uint8_t frame[5000],previous[5000];memcpy(previous,boot_screen,5000);
 paint(display,previous,true);int refreshes=0;
 for(;;){
  bool success=false;
  if(online){
   if(stop_pending.exchange(false) && !request("/stop",nullptr))stop_pending=true;
   char path[48];snprintf(path,sizeof(path),"/screen.bin?page=%d",page.load());
   success=request(path,frame);
  }
  if(!success)memcpy(frame,boot_screen,5000);
  if(memcmp(frame,previous,5000)){
   paint(display,frame,++refreshes%20==0);memcpy(previous,frame,5000);
   ESP_LOGI(TAG,"Screen updated page=%d backend=%s",page.load(),success?"online":"offline");
  }
  ulTaskNotifyTake(pdTRUE,pdMS_TO_TICKS(15000));
 }
}
static void stop_now(){
 stopped=true;stop_pending=true;controller_release();page=1;
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
  if(down&&held&&!long_sent&&now-began>=1200){long_sent=true;stop_now();}
  if(!down&&held){held=false;if(!long_sent&&now-began>=50){page=1-page.load();if(screen_task_handle)xTaskNotifyGive(screen_task_handle);}}
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
static void console_task(void*){
 char line[256];
 for(;;){
  if(!fgets(line,sizeof(line),stdin)){vTaskDelay(pdMS_TO_TICKS(100));continue;}
  line[strcspn(line,"\r\n")]=0;
  if(strcmp(line,"STOP")==0)stop_now();
  else if(strcmp(line,"PAGE")==0){page=1-page.load();xTaskNotifyGive(screen_task_handle);}
  else if(strcmp(line,"STATUS")==0)printf("STATUS wifi=%d usb=%d page=%d stopped=%d psram=%u\n",online.load(),controller_usb_ready(),page.load(),stopped.load(),(unsigned)esp_psram_get_size());
  else if(strncmp(line,"WIFI\t",5)==0){
   char *split=strchr(line+5,'\t');
   if(split && split-line-5<=32 && strlen(split+1)<=64){
    *split=0;nvs_handle_t h;if(nvs_open("wifi",NVS_READWRITE,&h)==ESP_OK){nvs_set_str(h,"ssid",line+5);nvs_set_str(h,"password",split+1);nvs_commit(h);nvs_close(h);printf("WiFi saved; restarting\n");fflush(stdout);vTaskDelay(pdMS_TO_TICKS(300));esp_restart();}
   }
   memset(line,0,sizeof(line));
  }
 }
}
extern "C" void app_main(){
 ESP_ERROR_CHECK(nvs_flash_init());
 gpio_config_t power={};power.pin_bit_mask=(1ULL<<6)|(1ULL<<42)|(1ULL<<17);power.mode=GPIO_MODE_OUTPUT;
 ESP_ERROR_CHECK(gpio_config(&power));gpio_set_level(GPIO_NUM_6,0);gpio_set_level(GPIO_NUM_42,1);gpio_set_level(GPIO_NUM_17,1);
 gpio_config_t button={};button.pin_bit_mask=(1ULL<<0)|(1ULL<<18);button.mode=GPIO_MODE_INPUT;button.pull_up_en=GPIO_PULLUP_ENABLE;ESP_ERROR_CHECK(gpio_config(&button));
 controller_usb_start();
 xTaskCreate(screen_task,"screen",24576,nullptr,3,&screen_task_handle);
 xTaskCreate(input_task,"button",3072,nullptr,5,nullptr);
 xTaskCreate(console_task,"console",4096,nullptr,2,nullptr);
 wifi_start();
 ESP_LOGI(TAG,"Epaper controller boot: PSRAM=%u; no automatic HID actions",(unsigned)esp_psram_get_size());
}
