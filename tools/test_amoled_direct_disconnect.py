"""Execute the production GAP disconnect branch with synthetic connection handles."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
source=(root/"firmware-amoled/main/relay.c").read_text()
start=source.index("}else if(e->type==BLE_GAP_EVENT_DISCONNECT){")
brace=source.index("{",start);end=brace+1;depth=1
while depth:
 depth+=(source[end]=="{")-(source[end]=="}");end+=1
branch=source[brace+1:end-1]
code=r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#define BLE_HS_CONN_HANDLE_NONE 65535
#define taskENTER_CRITICAL(p) ((void)(p))
#define taskEXIT_CRITICAL(p) ((void)(p))
static int mux;
static uint16_t connection;
static bool active,auth_ready,gate,direct_running;
static uint8_t key[32],auth_proof[32];
static unsigned cancels,ota_cancels,adverts;
static void amoled_ota_disconnect(void){ota_cancels++;}
static void amoled_relay_cancel(void){cancels++;direct_running=false;gate=false;}
static void advertise(void){adverts++;}
struct Event {struct {struct {uint16_t conn_handle;} conn;} disconnect;};
static void disconnected(uint16_t handle){
 struct Event event={.disconnect.conn.conn_handle=handle};struct Event *e=&event;(void)e;
"""
code+=branch+"\n}\n"
code+=r"""
int main(void){
 connection=BLE_HS_CONN_HANDLE_NONE;active=false;auth_ready=false;gate=direct_running=true;
 disconnected(17);
 assert(direct_running&&gate&&!cancels&&!ota_cancels&&connection==BLE_HS_CONN_HANDLE_NONE);
 connection=8;active=auth_ready=true;
 memset(key,1,sizeof(key));memset(auth_proof,2,sizeof(auth_proof));
 disconnected(17);
 assert(active&&auth_ready&&connection==8&&direct_running&&gate&&!cancels&&!ota_cancels);
 disconnected(8);
 assert(!active&&!auth_ready&&connection==BLE_HS_CONN_HANDLE_NONE&&cancels==1&&ota_cancels==1);
 for(unsigned i=0;i<32;i++)assert(!key[i]&&!auth_proof[i]);
 puts("Production GAP disconnect: rejected/stale handles preserve owner; current BLE owner cancels safely");
}
"""
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/"test.c").write_text(code)
 subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror","-fsanitize=address,undefined",str(p/"test.c"),"-o",str(p/"test")],check=True)
 subprocess.run([str(p/"test")],check=True)

