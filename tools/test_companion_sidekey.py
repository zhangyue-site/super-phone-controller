from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[1];s=(r/'firmware-amoled/main/main.c').read_text();a=s.index('static void keys_poll(void){');b=s.index('static lv_obj_t *status_chip',a);fn=s[a:b]
code=r"""
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <assert.h>
enum {GPIO_NUM_0,GPIO_NUM_18};
static bool boot,side,ready=true,armed,ota,transferring,audio,pending_power,refresh;
static unsigned page,arms,cancels,side_hold_ms;static int display_idle,power_request;static char notice[100];static int64_t now;
#define atomic_load(x) (*(x))
#define ESP_LOGI(...) ((void)0)
static int64_t esp_timer_get_time(void){return now;}
static int gpio_get_level(int n){return !(n==GPIO_NUM_0?boot:side);}
static void amoled_display_idle_activity(int *p,uint32_t n){(void)p;(void)n;}
static void amoled_audio_cancel(void){cancels++;}
static bool amoled_audio_busy(void){return audio;}
static bool amoled_ota_busy(void){return ota;}
static bool amoled_wifi_transferring(void){return transferring;}
static bool amoled_usb_ready(void){return ready;}
static bool amoled_usb_armed(void){return armed;}
static void amoled_usb_gate(bool v){armed=v;arms++;}
static bool amoled_power_take_short_press(void){return false;}
"""
tests=r"""
static void ticks(unsigned n){while(n--){now+=20000;keys_poll();}}
static void release(void){side=boot=false;ticks(2);armed=false;}
int main(void){
 side=true;ticks(100);assert(!arms);release();
 side=true;ticks(20);side=false;ticks(1);assert(!arms&&page==11);
 boot=true;ticks(100);boot=false;ticks(1);assert(!arms);
 side=true;ticks(61);assert(arms==1&&armed&&page==4);ticks(40);assert(arms==1);release();
 side=true;ticks(30);ready=false;ticks(1);ready=true;ticks(80);assert(arms==1);release();
 side=true;ota=true;ticks(10);ota=false;ticks(80);assert(arms==1);release();
 side=true;ticks(20);now+=300000;ticks(80);assert(arms==1);release();
 side=true;audio=true;ticks(10);audio=false;ticks(80);assert(arms==1);release();
 side=true;ticks(61);assert(arms==2);release();
 puts("Recovered GPIO18 grant: startup hold, short press, BOOT exclusion, 1.2s hold, no repeat, detach, gap, OTA and voice exclusion passed");
}
"""
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(code+fn+tests)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
