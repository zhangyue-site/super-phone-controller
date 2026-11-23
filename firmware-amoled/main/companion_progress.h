#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
typedef enum {PC_IDLE,PC_PLAN,PC_CONFIRM,PC_QUEUE,PC_RECOGNIZE,PC_DISPATCH,PC_OPERATE,PC_VERIFY,PC_DONE,PC_ERROR,PC_STOPPING,PC_STOPPED,PC_UNKNOWN} pc_phase;
typedef enum {PC_PENDING,PC_CURRENT,PC_COMPLETE,PC_FAILED} pc_row;
typedef struct {unsigned epoch,revision,round;pc_phase phase;pc_row rows[8];char task[65],detail[192];int64_t updated_ms;bool sealed;} pc_companion;
static inline void pc_companion_begin(pc_companion *s,unsigned epoch,const char *task){
 memset(s,0,sizeof(*s));s->epoch=epoch;snprintf(s->task,sizeof(s->task),"%s",task?task:"");
}
static inline bool pc_companion_apply(pc_companion *s,unsigned epoch,unsigned revision,pc_phase phase,unsigned round,unsigned completed,bool verified){
 if(epoch!=s->epoch||revision<=s->revision||(s->sealed&&!(s->phase==PC_STOPPING&&phase==PC_STOPPED)))return false;
 int failed_row=-1;for(unsigned i=0;i<8;i++)if(s->rows[i]==PC_CURRENT)failed_row=(int)i;
 s->revision=revision;s->round=round;
 if(phase==PC_DONE&&!verified)phase=PC_ERROR;
 s->phase=phase;
 for(unsigned i=0;i<8;i++)s->rows[i]=(completed&(1u<<i))?PC_COMPLETE:PC_PENDING;
 int row=phase==PC_PLAN?1:phase==PC_CONFIRM?2:phase==PC_RECOGNIZE?3:phase==PC_DISPATCH?4:phase==PC_OPERATE?5:phase==PC_VERIFY?6:-1;
 if(row>=0)s->rows[row]=PC_CURRENT;
 if(phase==PC_DONE){s->rows[6]=s->rows[7]=PC_COMPLETE;s->sealed=true;}
 if(phase==PC_ERROR&&failed_row>=0)s->rows[failed_row]=PC_FAILED;
 if(phase==PC_ERROR||phase==PC_STOPPED)s->sealed=true;
 return true;
}
#define pc_companion_event pc_companion_apply
static inline bool pc_companion_update(pc_companion *s,unsigned epoch,unsigned revision,pc_phase phase,unsigned round,unsigned completed,bool verified){return pc_companion_apply(s,epoch,revision,phase,round,completed,verified);}
static inline void pc_companion_stop(pc_companion *s){if(s->phase!=PC_IDLE&&!s->sealed){s->phase=PC_STOPPING;s->sealed=true;}}
