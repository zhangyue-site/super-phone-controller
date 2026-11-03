"""Exercise production relay mux arbitration for the audio owner."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/"firmware-amoled/main/relay.c").read_text()
def fn(name):
 start=s.index(name+"(");start=s.rfind("\n",0,start)+1
 brace=s.index("{",start);end=brace+1;depth=1
 while depth:
  depth+=(s[end]=="{")-(s[end]=="}");end+=1
 return s[start:end]
code=r"""
#include <stdbool.h>
#include <assert.h>
#include <stdio.h>
#define BLE_HS_CONN_HANDLE_NONE 65535
#define taskENTER_CRITICAL(p) ((void)(p))
#define taskEXIT_CRITICAL(p) ((void)(p))
static int mux,connection=65535;
static bool active,busy,direct_owner,audio_owner;
"""
code+="\n".join(fn(n) for n in ["amoled_relay_direct_acquire","amoled_relay_direct_release","amoled_relay_audio_acquire","amoled_relay_audio_owned","amoled_relay_audio_release"])
code+=r"""
int main(void){
 active=true;assert(!amoled_relay_audio_acquire());active=false;
 connection=1;assert(!amoled_relay_audio_acquire());connection=65535;
 busy=true;assert(!amoled_relay_audio_acquire());busy=false;
 assert(amoled_relay_direct_acquire());assert(!amoled_relay_audio_acquire());amoled_relay_direct_release();
 assert(amoled_relay_audio_acquire());assert(amoled_relay_audio_owned());
 assert(!amoled_relay_direct_acquire());assert(!amoled_relay_audio_acquire());
 amoled_relay_audio_release();assert(!amoled_relay_audio_owned());assert(amoled_relay_direct_acquire());
 puts("Production audio owner mux: BLE/direct/busy exclusion and release passed");
}
"""
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/"test.c").write_text(code)
 subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror","-fsanitize=address,undefined",str(p/"test.c"),"-o",str(p/"test")],check=True)
 subprocess.run([str(p/"test")],check=True)

