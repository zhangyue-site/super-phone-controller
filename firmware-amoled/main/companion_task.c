#include "companion_task.h"
#include "freertos/FreeRTOS.h"
#include "esp_timer.h"
static portMUX_TYPE lock=portMUX_INITIALIZER_UNLOCKED;
static pc_companion states[3];
static unsigned fences[3],stop_generation;
static bool stop_barrier;
static char stop_task[65];
static const char *str(const cJSON *o,const char *key){const cJSON *v=cJSON_GetObjectItemCaseSensitive(o,key);return cJSON_IsString(v)?v->valuestring:"";}
static void copy_detail(char *dst,size_t capacity,const char *src){
 if(!src)src="";
 size_t n=strlen(src);
 if(n>=capacity){n=capacity-1;while(n>0&&((unsigned char)src[n]&0xc0)==0x80)n--;}
 memcpy(dst,src,n);dst[n]=0;
}
static unsigned selected(void){
 unsigned pick=states[1].updated_ms>states[0].updated_ms?1:0;
 if(states[2].updated_ms>states[pick].updated_ms&&states[2].phase!=PC_IDLE)pick=2;
 if(states[0].phase!=PC_IDLE&&!states[0].sealed)pick=0;
 if(states[2].task[0]&&states[2].updated_ms>=states[pick].updated_ms&&(!states[0].task[0]||states[0].phase==PC_IDLE||states[0].sealed||!strcmp(states[0].task,states[2].task)))pick=2;
 if(pick!=2&&states[0].task[0]&&!strcmp(states[0].task,states[1].task)){
  if(states[0].sealed)pick=0;
  else if(states[1].phase!=PC_IDLE&&states[1].phase!=PC_UNKNOWN)pick=1;
 }
 return pick;
}
void amoled_companion_begin(unsigned source,unsigned epoch,const char *task){
 if(source>2)return;
 taskENTER_CRITICAL(&lock);
 if(!(source==2&&stop_barrier)&&epoch>=fences[source]&&!(states[source].epoch==epoch&&states[source].revision)){
  if(source<2&&stop_barrier){stop_barrier=false;stop_generation++;}
  pc_companion_begin(&states[source],epoch,task);states[source].updated_ms=esp_timer_get_time()/1000;
 }
 taskEXIT_CRITICAL(&lock);
}
void amoled_companion_event(unsigned source,unsigned epoch,pc_phase phase,unsigned round,unsigned completed,const char *detail,bool verified){
 if(source>2)return;
 taskENTER_CRITICAL(&lock);pc_companion *s=&states[source];
 if(pc_companion_apply(s,epoch,s->revision+1,phase,round,completed,verified)){
  copy_detail(s->detail,sizeof(s->detail),detail);s->updated_ms=esp_timer_get_time()/1000;
 }
 taskEXIT_CRITICAL(&lock);
}
static bool hex_id(const char *id){
 if(strlen(id)!=32)return false;
 for(unsigned i=0;i<32;i++)if(!((id[i]>='0'&&id[i]<='9')||(id[i]>='a'&&id[i]<='f')))return false;
 return true;
}
static void remote_reply(unsigned source,unsigned epoch,const cJSON *reply,bool guarded,unsigned requested_stop){
 if(source>2||!reply)return;
 const char *id=str(reply,"task_id"),*state=str(reply,"state");
 const cJSON *p=cJSON_GetObjectItemCaseSensitive(reply,"progress");
 pc_phase phase=PC_UNKNOWN;unsigned round=0,bits=0;
 bool verified=cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(reply,"verified"));
 if(!strcmp(state,"pending")){phase=PC_CONFIRM;bits=3;}
 else if(!strcmp(state,"queued")){phase=PC_QUEUE;bits=7;}
 else if(!strcmp(state,"running"))phase=PC_UNKNOWN;
 else if(!strcmp(state,"done"))phase=PC_DONE;
 else if(!strcmp(state,"stopped")||!strcmp(state,"cancelled"))phase=PC_STOPPED;
 else if(*state&&strcmp(state,"idle"))phase=PC_ERROR;
 if(cJSON_IsObject(p)){
  static const char *names[]={"idle","planning","confirming","queued","recognizing","dispatching","operating","verifying","done","error","stopping","stopped","unknown"};
  const char *value=str(p,"phase");
  for(unsigned i=0;i<sizeof(names)/sizeof(*names);i++)if(!strcmp(value,names[i]))phase=(pc_phase)i;
  const cJSON *v=cJSON_GetObjectItemCaseSensitive(p,"round");if(cJSON_IsNumber(v)&&v->valuedouble>=0&&v->valuedouble<=10000)round=v->valueint;
  v=cJSON_GetObjectItemCaseSensitive(p,"completed");if(cJSON_IsNumber(v)&&v->valuedouble>=0&&v->valuedouble<=255)bits=v->valueint;
 }
 if(phase==PC_DONE&&strcmp(state,"done"))phase=PC_UNKNOWN;
 taskENTER_CRITICAL(&lock);
 if(guarded&&requested_stop!=stop_generation){taskEXIT_CRITICAL(&lock);return;}
 if(source==2&&stop_barrier){
  bool confirms=!strcmp(state,"idle")||((!strcmp(state,"stopped")||!strcmp(state,"cancelled"))&&stop_task[0]&&!strcmp(id,stop_task));
  if(confirms){
   pc_companion *s=&states[2];s->phase=PC_STOPPED;s->sealed=true;s->updated_ms=esp_timer_get_time()/1000;
   snprintf(s->task,sizeof(s->task),"%s",stop_task);snprintf(s->detail,sizeof(s->detail),"云端已确认停止，本地输入已撤销");
   stop_barrier=false;stop_generation++;
  }
  taskEXIT_CRITICAL(&lock);return;
 }
 pc_companion *s=&states[source];
 if(source==2&&guarded&&hex_id(id)&&strcmp(s->task,id))pc_companion_begin(s,epoch,id);
 bool current=s->epoch==epoch&&(!s->task[0]||!*id||!strcmp(s->task,id));
 if(current&&hex_id(id)&&!s->task[0])snprintf(s->task,sizeof(s->task),"%s",id);
 if(current&&strcmp(state,"idle")&&pc_companion_apply(s,epoch,s->revision+1,phase,round,bits,verified)){
  copy_detail(s->detail,sizeof(s->detail),str(reply,"reply"));s->updated_ms=esp_timer_get_time()/1000;
 }
 taskEXIT_CRITICAL(&lock);
}
void amoled_companion_remote(unsigned source,unsigned epoch,const cJSON *reply){remote_reply(source,epoch,reply,false,0);}
unsigned amoled_companion_stop_generation(void){taskENTER_CRITICAL(&lock);unsigned n=stop_generation;taskEXIT_CRITICAL(&lock);return n;}
void amoled_companion_monitor_result(unsigned epoch,unsigned requested_stop,const cJSON *reply){remote_reply(2,epoch,reply,true,requested_stop);}
void amoled_companion_stop(void){
 taskENTER_CRITICAL(&lock);
 snprintf(stop_task,sizeof(stop_task),"%s",states[selected()].task);stop_barrier=true;stop_generation++;
 if(states[2].phase==PC_IDLE){states[2].phase=PC_STOPPING;states[2].sealed=true;}
 for(unsigned i=0;i<3;i++){
  pc_companion_stop(&states[i]);
  if(states[i].phase==PC_STOPPING){snprintf(states[i].detail,sizeof(states[i].detail),"本地输入已撤销，云端停止待确认");states[i].updated_ms=esp_timer_get_time()/1000;}
 }
 taskEXIT_CRITICAL(&lock);
}
void amoled_companion_fence(unsigned source,unsigned epoch){
 if(source>2)return;
 taskENTER_CRITICAL(&lock);if(epoch>fences[source])fences[source]=epoch;taskEXIT_CRITICAL(&lock);
}
void amoled_companion_stop_ack(unsigned source){
 /* Plugin worker calls this only for its exact serialized stop request. Monitor
  * confirmations must use monitor_result with task ID and pre-request epoch. */
 if(source>1)return;
 taskENTER_CRITICAL(&lock);pc_companion *s=&states[source];
 if(s->phase==PC_STOPPING){
  s->phase=PC_STOPPED;s->updated_ms=esp_timer_get_time()/1000;snprintf(s->detail,sizeof(s->detail),"云端已确认停止，本地输入已撤销");
  if(stop_task[0]&&!strcmp(s->task,stop_task)){stop_barrier=false;stop_generation++;}
 }
 taskEXIT_CRITICAL(&lock);
}
void amoled_companion_snapshot(pc_companion *out){
 taskENTER_CRITICAL(&lock);*out=states[selected()];taskEXIT_CRITICAL(&lock);
 if(!out->sealed&&out->phase!=PC_IDLE&&esp_timer_get_time()/1000-out->updated_ms>15000){
  out->phase=PC_UNKNOWN;for(unsigned i=0;i<8;i++)if(out->rows[i]==PC_CURRENT)out->rows[i]=PC_PENDING;
  snprintf(out->detail,sizeof(out->detail),"状态已超时，等待新回执；请在手机核对");
 }
}
