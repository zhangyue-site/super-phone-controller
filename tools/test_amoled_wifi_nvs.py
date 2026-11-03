from pathlib import Path
import tempfile,subprocess
root=Path(__file__).resolve().parents[1];s=(root/'firmware-amoled/main/wifi.c').read_text();a=s.index('esp_err_t amoled_wifi_start(void)');b=s.index('\nstatic esp_err_t runtime_initialize',a)
code=r'''
#include <assert.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include "wifi_policy.h"
#define ESP_OK 0
#define ESP_ERR_NO_MEM -1
#define NVS_READONLY 0
typedef int esp_err_t;
typedef int nvs_handle_t;
typedef struct {uint32_t schema;char ssid[33],password[64],endpoint[191];} PrivateConfig;
typedef struct {uint32_t schema;char ssid[33],password[64],endpoint[191];char backup_ssid[33],backup_password[64];uint32_t automatic;} MultiConfig;
static MultiConfig config,stored;
static atomic_bool configured,auto_enabled,ready;
static int mutex,starts;static size_t blob_size;
static int xSemaphoreCreateMutex(void){return 1;}
static int nvs_open(const char *n,int mode,int *h){(void)n;(void)mode;*h=1;return 0;}
static int nvs_get_blob(int h,const char *k,void *out,size_t *n){(void)h;(void)k;assert(*n>=blob_size);memcpy(out,&stored,blob_size);*n=blob_size;return 0;}
static void nvs_close(int h){(void)h;}
static int runtime_start(void){starts++;return 0;}
'''+s[a:b]+r'''
static void reset(void){memset(&config,0,sizeof(config));memset(&stored,0,sizeof(stored));atomic_store(&configured,false);atomic_store(&auto_enabled,false);starts=0;strcpy(stored.ssid,"test-home");strcpy(stored.password,"test-pass");strcpy(stored.endpoint,"https://controller.test");blob_size=sizeof(stored);stored.schema=2;}
int main(void){
 reset();stored.schema=1;blob_size=sizeof(PrivateConfig);assert(!amoled_wifi_start()&&configured&&!auto_enabled&&starts==1);
 reset();strcpy(stored.backup_ssid,"test-office");strcpy(stored.backup_password,"test-pass2");stored.automatic=1;assert(!amoled_wifi_start()&&configured&&auto_enabled&&starts==1);
 reset();stored.schema=9;amoled_wifi_start();assert(!configured&&!starts);
 reset();memset(stored.endpoint,'x',sizeof(stored.endpoint));strcpy(stored.backup_ssid,"test-office");amoled_wifi_start();assert(!configured&&!starts);
 reset();strcpy(stored.backup_ssid,"test-office");strcpy(stored.backup_password,"short");amoled_wifi_start();assert(!configured&&!starts);
 reset();stored.automatic=2;amoled_wifi_start();assert(!configured&&!starts);
 puts("Production NVS loader: legacy migration, dual-profile persistence, malformed strings/schema/flags rejected");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root/'firmware-amoled/main'),str(p/'test.c'),str(root/'firmware-amoled/main/wifi_policy.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
