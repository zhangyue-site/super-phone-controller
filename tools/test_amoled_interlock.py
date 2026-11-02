"""Execute production HID permission/gate functions with a deterministic mutex."""
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[1]
s=(r/'firmware-amoled/main/usb.c').read_text()
def fn(name):
 start=s.index(name+'(');start=s.rfind('\n',0,start)+1;brace=s.index('{',start);i=brace+1;depth=1
 while depth:depth+=(s[i]=='{')-(s[i]=='}');i+=1
 return s[start:i]
code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
static bool armed,ota,held;static void *input_mutex=(void*)1;
#define pdTRUE 1
static int xSemaphoreTake(void *s,int wait){if(held)return 0;held=true;return 1;}
static void xSemaphoreGive(void *s){held=false;}
static bool amoled_usb_ready(void){return true;}
static bool amoled_ota_busy(void){return ota;}
static void release_all(void){}
'''
code+='\n'.join(fn(n) for n in ['permitted','amoled_usb_reserve_ota','amoled_usb_gate'])
code+=r'''
static bool reserve(void){amoled_usb_gate(true);assert(!armed);ota=true;return true;}
int main(void){
 assert(amoled_usb_reserve_ota(reserve));assert(ota&&!armed);amoled_usb_gate(true);assert(!armed);
 armed=true;assert(!permitted(false,NULL,0));assert(permitted(true,NULL,0));
 armed=false;ota=false;amoled_usb_gate(true);assert(armed);assert(!amoled_usb_reserve_ota(reserve));
 amoled_usb_gate(false);assert(!armed);held=true;assert(!amoled_usb_reserve_ota(reserve));
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('AMOLED HID/OTA interlock and release-only permission passed')
