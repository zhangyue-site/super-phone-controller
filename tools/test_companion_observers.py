"""Execute production observer adapter with real cJSON; no devices/network."""
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[1]
code=r"""
#include "companion_task.h"
#include <assert.h>
static int64_t clock_ms=1000;
int64_t esp_timer_get_time(void){return clock_ms*1000;}
static void remote(unsigned source,unsigned epoch,const char *json){cJSON *o=cJSON_Parse(json);assert(o);amoled_companion_remote(source,epoch,o);cJSON_Delete(o);}
int main(void){
 pc_companion s;
 amoled_companion_begin(0,1,"");amoled_companion_event(0,1,PC_PLAN,0,0,"planning",false);
 remote(0,1,"{\"task_id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"state\":\"pending\"}");
 amoled_companion_snapshot(&s);assert(s.phase==PC_CONFIRM&&s.rows[0]==PC_COMPLETE);
 clock_ms++;
 amoled_companion_begin(1,9,"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");amoled_companion_event(1,9,PC_OPERATE,1,0,"old direct",false);
 amoled_companion_snapshot(&s);assert(s.phase==PC_CONFIRM); /* new plugin not overwritten */
 remote(0,1,"{\"task_id\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"state\":\"done\",\"verified\":true}");
 amoled_companion_snapshot(&s);assert(s.phase==PC_CONFIRM);
 clock_ms++;amoled_companion_stop();amoled_companion_fence(0,2);amoled_companion_fence(1,10);
 amoled_companion_begin(0,1,"");remote(0,1,"{\"task_id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"state\":\"done\",\"verified\":true}");
 amoled_companion_snapshot(&s);assert(s.phase==PC_STOPPING);
 clock_ms++;amoled_companion_stop_ack(0);amoled_companion_snapshot(&s);assert(s.phase==PC_STOPPED);
 clock_ms++;amoled_companion_begin(0,2,"");amoled_companion_event(0,2,PC_PLAN,0,0,"new plan",false);
 remote(0,2,"{\"task_id\":\"cccccccccccccccccccccccccccccccc\",\"state\":\"running\",\"progress\":{\"phase\":\"recognizing\",\"round\":2,\"completed\":7}}");
 amoled_companion_snapshot(&s);assert(s.phase==PC_RECOGNIZE&&s.round==2&&s.rows[3]==PC_CURRENT);
 amoled_companion_begin(0,2,"");amoled_companion_snapshot(&s);assert(s.phase==PC_RECOGNIZE); /* no reset */
 clock_ms+=16000;amoled_companion_snapshot(&s);assert(s.phase==PC_UNKNOWN);
 remote(0,2,"{\"task_id\":\"cccccccccccccccccccccccccccccccc\",\"state\":\"running\",\"verified\":true,\"progress\":{\"phase\":\"done\"}}");
 amoled_companion_snapshot(&s);assert(s.phase==PC_UNKNOWN); /* inner field never certifies success */
 unsigned pre_stop=amoled_companion_stop_generation();clock_ms++;amoled_companion_stop();
 amoled_companion_begin(2,1,"cccccccccccccccccccccccccccccccc");
 remote(2,1,"{\"task_id\":\"cccccccccccccccccccccccccccccccc\",\"state\":\"running\"}");
 amoled_companion_snapshot(&s);assert(s.phase==PC_STOPPING);
 cJSON *old=cJSON_Parse("{\"task_id\":\"cccccccccccccccccccccccccccccccc\",\"state\":\"stopped\"}");
 amoled_companion_monitor_result(1,pre_stop,old);amoled_companion_snapshot(&s);assert(s.phase==PC_STOPPING);
 cJSON *other=cJSON_Parse("{\"task_id\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"state\":\"stopped\"}");
 amoled_companion_monitor_result(1,amoled_companion_stop_generation(),other);amoled_companion_snapshot(&s);assert(s.phase==PC_STOPPING);
 clock_ms++;amoled_companion_monitor_result(1,amoled_companion_stop_generation(),old);amoled_companion_snapshot(&s);assert(s.phase==PC_STOPPED);
 cJSON_Delete(old);cJSON_Delete(other);
 return 0;
}
"""
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'freertos').mkdir();(p/'freertos/FreeRTOS.h').write_text('#pragma once\ntypedef int portMUX_TYPE;\n#define portMUX_INITIALIZER_UNLOCKED 0\n#define taskENTER_CRITICAL(p) ((void)(p))\n#define taskEXIT_CRITICAL(p) ((void)(p))\n')
 (p/'esp_timer.h').write_text('#include <stdint.h>\nint64_t esp_timer_get_time(void);\n');(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(p),'-I',str(r/'firmware-amoled/main'),'-I',str(r/'evidence/cjson'),str(p/'test.c'),str(r/'firmware-amoled/main/companion_task.c'),str(r/'evidence/cjson/cJSON.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('Production observers: source isolation, task binding, STOP fence/ACK, stale/unknown and verified-only completion passed')
