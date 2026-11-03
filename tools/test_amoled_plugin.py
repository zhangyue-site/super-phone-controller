"""Production plugin state machine with synthetic server responses; no real API."""
from pathlib import Path
import argparse,subprocess,tempfile,re
root=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument("--cjson-dir",required=True);args=ap.parse_args();deps=Path(args.cjson_dir)
s=(root/"firmware-amoled/main/plugin.c").read_text()
def fn(name):
 start=re.search(r"\b"+re.escape(name)+r"\(",s).start();start=s.rfind("\n",0,start)+1
 brace=s.index("{",start);end=brace+1;depth=1
 while depth:
  depth+=(s[end]=="{")-(s[end]=="}");end+=1
 return s[start:end]
code=r"""
#include "cJSON.h"
#include <stdatomic.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <setjmp.h>
#include <assert.h>
#define taskENTER_CRITICAL(p) ((void)(p))
#define taskEXIT_CRITICAL(p) ((void)(p))
#define pdTRUE 1
#define pdPASS 1
#define pdMS_TO_TICKS(n) (n)
typedef struct {unsigned op,epoch,direct_epoch;char entry[97],parameters[1025];} Request;
static void *queue;
static atomic_bool started,busy,stop_requested;
static atomic_uint generation=1,stage;
static int text_lock;
static char reply_text[1024],session[33],task_id[33],confirmation[33];
static int64_t pending_until;
static Request queued;static bool queued_valid;
static jmp_buf paused;
static unsigned enables,cancels,stops,prepares,confirms,direct_epoch=1;static bool cancel_before_enable,gate;static bool enable_ok=true,late_stop,unconfigured,bad_transition;
static void amoled_plugin_cancel(void);
static bool amoled_identity_ready(void){return true;}
static bool amoled_wifi_connected(void){return true;}
static bool amoled_relay_connected(void){return false;}
static bool amoled_relay_direct_owned(void){return false;}
static bool amoled_relay_audio_owned(void){return false;}
static bool amoled_ota_busy(void){return false;}
static void amoled_direct_cancel(void){cancels++;direct_epoch++;gate=false;}
static unsigned amoled_direct_epoch(void){return direct_epoch;}
static void amoled_usb_gate(bool enabled){assert(!enabled);}
static bool amoled_direct_enable_task_epoch(const char *id,unsigned expected){assert(!strcmp(id,"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"));enables++;if(cancel_before_enable)amoled_plugin_cancel();if(expected!=direct_epoch)return false;gate=enable_ok;return enable_ok;}
static int64_t esp_timer_get_time(void){return 1000;}
static void esp_fill_random(void *p,size_t n){memset(p,1,n);}
static void amoled_hex(const uint8_t *p,size_t n,char *out){(void)p;memset(out,'b',n*2);out[n*2]=0;}
static void *xQueueCreate(unsigned count,unsigned size){assert(count==1&&size==sizeof(Request));return (void *)1;}
static int xQueueSend(void *q,const Request *request,unsigned timeout){(void)q;(void)timeout;if(queued_valid)return 0;queued=*request;queued_valid=true;return 1;}
static int xQueueReceive(void *q,Request *request,unsigned timeout){(void)q;(void)timeout;if(!queued_valid)longjmp(paused,1);*request=queued;queued_valid=false;return 1;}
static void vQueueDelete(void *q){(void)q;}
static int xTaskCreate(void (*fn)(void *),const char *name,unsigned stack,void *ctx,unsigned priority,void *out){
 (void)fn;(void)name;(void)ctx;(void)priority;(void)out;assert(stack==8192);return 1;
}
"""
code+="\n".join(fn(n) for n in ["amoled_plugin_stage","amoled_plugin_text","message","message_current","str","hex","live"])
code+=r"""
static cJSON *post(cJSON *body,unsigned epoch,bool stopping){
 (void)epoch;const char *op=str(body,"operation");
 if(!strcmp(op,"stop")){assert(stopping);stops++;return cJSON_Parse("{\"state\":\"stopped\"}");}
 assert(!stopping);
 if(!strcmp(op,"prepare")){
  prepares++;assert(!strcmp(str(body,"entry"),"synthetic.open"));
  if(late_stop)amoled_plugin_cancel();
  if(bad_transition)return cJSON_Parse("{\"state\":\"queued\",\"task_id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"reply\":\"unexpected queue\"}");
  if(unconfigured)return cJSON_Parse("{\"state\":\"rejected\",\"reply\":\"私有工作流未配置\"}");
  return cJSON_Parse("{\"state\":\"pending\",\"task_id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"confirmation\":\"cccccccccccccccccccccccccccccccc\",\"reply\":\"本次真实计划\"}");
 }
 if(!strcmp(op,"confirm")){confirms++;assert(!strcmp(str(body,"confirmation"),"cccccccccccccccccccccccccccccccc"));return cJSON_Parse("{\"state\":\"queued\",\"task_id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"reply\":\"已确认排队\"}");}
 return cJSON_Parse("{\"state\":\"running\",\"task_id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"reply\":\"真实运行状态\"}");
}
"""
code+="\n".join(fn(n) for n in ["request","stop_server","apply","worker","init","amoled_plugin_prepare","amoled_plugin_confirm","amoled_plugin_cancel"])
code+=r"""
static void pump(void){if(!setjmp(paused))worker(NULL);}
static void reset(void){
 started=busy=stop_requested=false;generation=1;stage=0;reply_text[0]=session[0]=task_id[0]=confirmation[0]=0;
 queued_valid=false;enables=cancels=stops=prepares=confirms=0;direct_epoch=1;cancel_before_enable=gate=false;enable_ok=true;late_stop=unconfigured=bad_transition=false;
}
int main(void){
 char text[1024];
 reset();assert(!amoled_plugin_confirm()&&!enables);
 assert(amoled_plugin_prepare("synthetic.open","{}"));assert(!prepares&&!enables);
 pump();assert(stage==1&&prepares==1&&!enables&&!confirms);
 assert(amoled_plugin_text(text,sizeof(text))&&!strcmp(text,"本次真实计划"));
 assert(amoled_plugin_confirm());assert(!confirms&&!enables);pump();
 assert(stage==2&&confirms==1&&enables==1);
 assert(!amoled_plugin_confirm());assert(!amoled_plugin_prepare("synthetic.open","{}"));
 amoled_plugin_cancel();pump();assert(stage==6&&stops==1&&cancels==1);
 reset();assert(amoled_plugin_prepare("synthetic.open","{}"));pump();cancel_before_enable=true;assert(amoled_plugin_confirm());pump();assert(!gate&&stage==6&&stops==1);
 reset();bad_transition=true;assert(amoled_plugin_prepare("synthetic.open","{}"));pump();assert(stage==5&&!enables&&stops==1);
 reset();unconfigured=true;assert(amoled_plugin_prepare("synthetic.open","{}"));pump();
 assert(stage==5&&!enables&&prepares==1);
 assert(amoled_plugin_text(text,sizeof(text))&&strstr(text,"未配置"));
 reset();late_stop=true;assert(amoled_plugin_prepare("synthetic.open","{}"));pump();
 assert(stage==6&&!enables&&stops==1);
 reset();assert(amoled_plugin_prepare("synthetic.open","{}"));pump();
 enable_ok=false;assert(amoled_plugin_confirm());pump();assert(stage==5&&stops==1&&enables==1);
 puts("Production plugin lifecycle: no import auto-run, plan before confirm, exact task permit, STOP/late reply, empty allowlist and failed local permit passed");
}
"""
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/"test.c").write_text(code)
 subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror","-Wno-unused-parameter","-fsanitize=address,undefined","-I",str(deps),str(p/"test.c"),str(deps/"cJSON.c"),"-o",str(p/"test")],check=True)
 subprocess.run([str(p/"test")],check=True)
