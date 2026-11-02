"""Production owner/board-local consent functions, with deterministic I/O."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
def fn(source,name):
 start=source.index(name+"(");start=source.rfind("\n",0,start)+1
 brace=source.index("{",start);end=brace+1;depth=1
 while depth:
  depth+=(source[end]=="{")-(source[end]=="}");end+=1
 return source[start:end]
relay=(root/"firmware-amoled/main/relay.c").read_text()
direct=(root/"firmware-amoled/main/direct.c").read_text()
code=r"""
#include <stdbool.h>
#include <stdint.h>
#include <stdatomic.h>
#include <assert.h>
#include <stdio.h>
#define taskENTER_CRITICAL(p) ((void)(p))
#define taskEXIT_CRITICAL(p) ((void)(p))
#define BLE_HS_CONN_HANDLE_NONE 65535
static int mux,connection=65535;
static bool active,busy,direct_owner;
static atomic_bool started=true,enabled,online;
static atomic_uint generation=1;
static atomic_llong action_until;
static bool identity=true,wifi=true,armed,ota,ota_ready=true,usb=true;
static int64_t now=1000000;
static int64_t esp_timer_get_time(void){return now;}
static bool amoled_identity_ready(void){return identity;}
static bool amoled_wifi_connected(void){return wifi;}
static bool amoled_usb_armed(void){return armed&&usb;}
static bool amoled_ota_busy(void){return ota;}
static bool amoled_ota_ready(void){return ota_ready;}
static bool amoled_relay_connected(void){return active||connection!=65535;}
static void amoled_usb_gate(bool value){armed=value&&usb&&!ota;}
"""
code+="\n".join(fn(relay,n) for n in ["amoled_relay_direct_acquire","amoled_relay_direct_owned","amoled_relay_direct_release"])
code+="\n"+"\n".join(fn(direct,n) for n in ["amoled_direct_cancel","live","amoled_direct_enable"])
code+=r"""
int main(void){
 amoled_usb_gate(true);assert(armed&&!enabled); /* Manual ARM grants no network permit. */
 active=true;assert(!amoled_relay_direct_acquire());assert(!amoled_direct_enable());active=false;
 connection=1;assert(!amoled_relay_direct_acquire());assert(!amoled_direct_enable());connection=65535;
 busy=true;assert(!amoled_relay_direct_acquire());busy=false;
 ota=true;assert(!amoled_direct_enable());ota=false;
 wifi=false;assert(!amoled_direct_enable());wifi=true;
 ota_ready=false;assert(!amoled_direct_enable());ota_ready=true;
 usb=false;assert(!amoled_direct_enable());usb=true;
 assert(amoled_direct_enable());assert(enabled&&action_until==21000000);
 assert(amoled_relay_direct_acquire());assert(amoled_relay_direct_owned());
 assert(!amoled_direct_enable()); /* Cannot re-arm while the previous owner retires. */
 unsigned epoch=atomic_load(&generation);assert(live(epoch));
 now=21000000;assert(!live(epoch));now=1000000;
 amoled_direct_cancel();assert(!enabled&&!live(epoch));
 amoled_usb_gate(true);assert(!enabled&&!live(epoch));
 amoled_relay_direct_release();assert(!amoled_relay_direct_owned());
 assert(amoled_direct_enable());assert(amoled_relay_direct_acquire());
 assert(live(atomic_load(&generation)));
 amoled_direct_cancel();amoled_relay_direct_release();
 puts("Production direct owner/consent: BLE/busy isolation, manual ARM separation, expiry and permanent STOP passed");
}
"""
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/"test.c").write_text(code)
 subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror","-fsanitize=address,undefined",str(p/"test.c"),"-o",str(p/"test")],check=True)
 subprocess.run([str(p/"test")],check=True)

