"""Run real idle policy and raw-touch/brightness adapters, without hardware."""
from pathlib import Path
import subprocess, tempfile
root=Path(__file__).resolve().parents[1]
source=(root/'firmware-amoled/main/main.c').read_text()
def function(name):
 start=source.rfind('\n',0,source.index(name+'('))+1
 a=source.index('{',start);depth=1;b=a+1
 while depth:
  depth+=(source[b]=='{')-(source[b]=='}');b+=1
 return source[start:b]
shim=r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include "display_idle.h"
#define ESP_OK 0
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
typedef int esp_err_t;
typedef void* esp_lcd_touch_handle_t;
typedef struct {int x,y;} esp_lcd_touch_point_data_t;
static amoled_display_idle_t display_idle;
static void *idle_panel;
static bool ota,deny_lock,held;
static int write_error,read_error,raw_count,write_count,last_brightness;
static int64_t now_us=1;
static int64_t esp_timer_get_time(void){return now_us;}
static bool amoled_ota_busy(void){return ota;}
static const char *esp_err_to_name(int e){(void)e;return "test";}
static int esp_lv_adapter_lock(int timeout){assert(timeout<=20);if(deny_lock)return 1;assert(!held);held=true;return ESP_OK;}
static bool bsp_display_lock(int timeout){return esp_lv_adapter_lock(timeout);}
static void esp_lv_adapter_unlock(void){assert(held);held=false;}
static void bsp_display_unlock(void){esp_lv_adapter_unlock();}
static int esp_lcd_panel_co5300_set_brightness(void *p,uint8_t brightness){(void)p;assert(held);write_count++;last_brightness=brightness;return write_error;}
static int esp_lcd_touch_read_data(void *p){(void)p;return read_error;}
static int esp_lcd_touch_get_data(void*p,esp_lcd_touch_point_data_t*points,uint8_t*count,uint8_t max){(void)p;(void)points;assert(max>=1);*count=raw_count;return 0;}
'''
main=r'''
int main(void){
 amoled_display_idle_init(&display_idle,0);
 now_us=60000000;display_idle_tick();assert(write_count==1&&last_brightness==30&&atomic_load(&display_idle.brightness)==30);
 now_us=300000000;display_idle_tick();assert(write_count==2&&last_brightness==0);
 uint8_t count=99;esp_lcd_touch_point_data_t point;
 raw_count=1;now_us=301000000;assert(idle_touch_read(NULL,&point,&count,1,NULL)==0&&count==0);
 deny_lock=true;display_idle_tick();assert(atomic_load(&display_idle.brightness)==0);
 deny_lock=false;now_us+=100000;write_error=1;display_idle_tick();assert(write_count==3);assert(atomic_load(&display_idle.brightness)==0);
 now_us+=1000000;write_error=0;display_idle_tick();assert(atomic_load(&display_idle.brightness)==100);
 assert(idle_touch_read(NULL,&point,&count,1,NULL)==0&&count==0); /* held wake */
 raw_count=0;assert(idle_touch_read(NULL,&point,&count,1,NULL)==0&&count==0); /* release */
 raw_count=1;assert(idle_touch_read(NULL,&point,&count,1,NULL)==0&&count==1); /* new press */
 raw_count=0;assert(idle_touch_read(NULL,&point,&count,1,NULL)==0&&count==0);
 read_error=1;count=99;assert(idle_touch_read(NULL,&point,&count,1,NULL)==1&&count==0);read_error=0;
 now_us+=400000000;display_idle_tick();assert(atomic_load(&display_idle.brightness)==0);
 ota=true;display_idle_tick();assert(atomic_load(&display_idle.brightness)==100);
 now_us+=400000000;ota=false;display_idle_tick();assert(atomic_load(&display_idle.brightness)==100);
 now_us+=60000000;display_idle_tick();assert(atomic_load(&display_idle.brightness)==30);
 assert(!held);return 0;
}
'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td);adapter=p/'adapter.c';adapter.write_text(shim+function('display_idle_tick')+function('idle_touch_read')+main)
 for name,src in [('policy',root/'tests/amoled_display_idle_test.c'),('adapters',adapter)]:
  exe=p/name
  subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-I'+str(root/'firmware-amoled/main'),str(src),str(root/'firmware-amoled/main/display_idle.c'),'-o',str(exe)],check=True)
  subprocess.run([str(exe)],check=True)
  print('Display idle '+name+' PASS',flush=True)
