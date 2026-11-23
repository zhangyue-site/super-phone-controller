"""Exercise actual display init against the observed S3 memory constraint.

The host model cannot replace an on-board DMA/Wi-Fi soak test.
"""
from pathlib import Path
import re, subprocess, tempfile, sys
root=Path(sys.argv[1])
source=(root/'firmware-amoled/main/main.c').read_text()
start=source.index('static lv_display_t *amoled_display_start(void)')
end=source.index('\nvoid app_main', start)
body=source[start:end]
prefix=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#define ESP_OK 0
#define BSP_LCD_H_RES 480
#define BSP_LCD_V_RES 480
#define ESP_LV_ADAPTER_DEFAULT_CONFIG() 0
#define ESP_LV_ADAPTER_ROTATE_0 0
#define ESP_LV_ADAPTER_TEAR_AVOID_MODE_NONE 0
#define ESP_LV_ADAPTER_PANEL_IF_OTHER 0
#define LV_EVENT_INVALIDATE_AREA 0
#define ESP_LV_ADAPTER_TOUCH_DEFAULT_CONFIG(d,t) {0}
typedef int lv_display_t;
typedef void* esp_lcd_panel_handle_t;
typedef void* esp_lcd_panel_io_handle_t;
typedef void* esp_lcd_touch_handle_t;
typedef struct {struct {void (*custom_touch_read)(void);} callbacks;} esp_lv_adapter_touch_config_t;
static void idle_touch_read(void){}
static void *idle_panel;
typedef struct {int lv_adapter_cfg,rotation,tear_avoid_mode;struct {int swap_xy,mirror_x,mirror_y;} touch_flags;} bsp_display_cfg_t;
typedef struct {size_t max_transfer_sz;} bsp_display_config_t;
typedef struct {void *panel,*panel_io;struct {int interface,rotation,hor_res,ver_res,buffer_height;bool use_psram,enable_ppa_accel,require_double_buffer;} profile;int tear_avoid_mode;} esp_lv_adapter_display_config_t;
static esp_lv_adapter_display_config_t actual;
static size_t max_transfer;
static int esp_lv_adapter_init(const void *p){(void)p;return 0;}
static int bsp_display_new(const bsp_display_config_t*c,void**p,void**i){max_transfer=c->max_transfer_sz;*p=(void*)1;*i=(void*)2;return 0;}
static lv_display_t *esp_lv_adapter_register_display(const esp_lv_adapter_display_config_t*c){actual=*c;static int d;return &d;}
static void amoled_rounder_cb(void){}
static void lv_display_add_event_cb(void*a,void(*b)(void),int c,void*d){(void)a;(void)b;(void)c;(void)d;}
static int bsp_touch_new(const bsp_display_cfg_t*c,void**p){(void)c;*p=(void*)1;return 0;}
static void *esp_lv_adapter_register_touch(void*p){return p;}
static int bsp_display_brightness_init(void){return 0;}
static int esp_lv_adapter_start(void){return 0;}
'''
main=r'''
int main(void){assert(amoled_display_start());
 size_t bytes=actual.profile.hor_res*actual.profile.buffer_height*2;
 assert(bytes<=max_transfer);
 /* A wide flush must still work at the observed largest free block (7168).
  * PSRAM requires a fresh same-sized internal bounce on ESP32-S3. */
 assert((!actual.profile.use_psram || bytes<=7168) && "observed fragmented heap cannot allocate display DMA bounce");
 /* Reserve a small draw buffer before Wi-Fi, so display traffic no longer
  * depends on any run-time contiguous allocation, even after fragmentation. */
 assert(!actual.profile.use_psram && "display still depends on transient DMA allocation");
 size_t reserved=bytes*(actual.profile.require_double_buffer?2:1);
 assert(reserved<=4096 && "reserve must fit low-memory Wi-Fi startup budget");
 assert(actual.profile.buffer_height%2==0);return 0;}
'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td)/'test.c';p.write_text(prefix+body+main);exe=Path(td)/'test'
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(p),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
print('AMOLED observed-fragmentation display regression PASS')
