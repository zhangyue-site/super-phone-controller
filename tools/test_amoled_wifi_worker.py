from pathlib import Path
import subprocess,tempfile
s=(Path(__file__).resolve().parents[1]/'firmware-amoled/main/wifi.c').read_text()
a=s.index('static void worker(');b=s.index('\nesp_err_t amoled_wifi_start',a)
code=r'''
#include <stdbool.h>
#include <stdatomic.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#define portMAX_DELAY 0
#define pdMS_TO_TICKS(x) (x)
#define WIFI_IF_STA 0
#define WIFI_AUTH_WPA2_PSK 2
#define ESP_OK 0
#define xSemaphoreTake(a,b) ((void)(a),(void)(b))
#define xSemaphoreGive(a) ((void)(a))
#define esp_wifi_start() ((void)0)
#define esp_wifi_stop() ((void)0)
typedef struct {uint32_t schema;char ssid[33],password[64],endpoint[191];char backup_ssid[33],backup_password[64];uint32_t automatic;} MultiConfig;
typedef struct {struct {unsigned char ssid[32],password[64];struct{int authmode;}threshold;struct{bool capable;}pmf_cfg;}sta;} wifi_config_t;
static MultiConfig config;
static atomic_uint config_generation=1,generation=1,stage,requested_epoch;
static atomic_bool configured=true,connected,requested,transfer,auto_enabled=true;
static bool automatic_download,armed,ble,direct;
static int mutex,calls,sets;static int64_t now,until;
static const char *available;static char chosen[33],seen[8][33];static jmp_buf done;
static int64_t esp_timer_get_time(void){return now;}
static int esp_wifi_disconnect(void){atomic_store(&connected,false);return 0;}
static int esp_wifi_set_config(int interface,const wifi_config_t *w){(void)interface;memcpy(chosen,w->sta.ssid,32);chosen[32]=0;assert(sets<8);strcpy(seen[sets++],chosen);return 0;}
static int esp_wifi_connect(void){atomic_store(&connected,available&&!strcmp(available,chosen));return 0;}
static bool amoled_usb_armed(void){return armed;}
static bool amoled_ota_busy(void){return false;}
static bool amoled_relay_connected(void){return ble;}
static bool amoled_relay_direct_owned(void){return direct;}
static bool amoled_identity_ready(void){return true;}
static void download(const char *endpoint,unsigned epoch){assert(!strcmp(endpoint,"https://controller.test")&&epoch==1&&automatic_download);calls++;}
static void vTaskDelay(int ticks){now+=(int64_t)ticks*1000;if(now>=until)longjmp(done,1);}
'''
code+=s[a:b]+r'''
static void reset(void){
 memset(&config,0,sizeof(config));strcpy(config.ssid,"home-test");strcpy(config.password,"test-only-password");strcpy(config.backup_ssid,"office-test");strcpy(config.backup_password,"test-only-password");strcpy(config.endpoint,"https://controller.test");
 now=0;until=90000000;sets=calls=0;armed=ble=direct=false;available=NULL;atomic_store(&connected,false);atomic_store(&configured,true);atomic_store(&auto_enabled,true);
}
static void run(void){if(!setjmp(done))worker(NULL);}
int main(void){
 reset();available="office-test";run();assert(sets==2&&!strcmp(seen[0],"home-test")&&!strcmp(seen[1],"office-test")&&connected&&calls==1);
 reset();available="home-test";run();assert(sets==1&&connected&&calls==1);
 reset();run();assert(sets>=4&&!connected&&!calls);
 reset();available="office-test";armed=true;run();assert(connected&&!calls);
 reset();available="office-test";ble=true;run();assert(connected&&!calls);
 reset();available="office-test";direct=true;run();assert(connected&&!calls);
 reset();available="office-test";atomic_store(&auto_enabled,false);run();assert(connected&&!calls);
 puts("Production worker: both Wi-Fi profiles, missing AP rotation, idle auto-update and HID/BLE/direct interlocks passed");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
