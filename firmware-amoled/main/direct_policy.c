#include "direct_policy.h"
#include <string.h>
static bool hex(const char *s,unsigned n){
 if(!s||strlen(s)!=n)return false;
 for(unsigned i=0;i<n;i++)if(!((s[i]>='0'&&s[i]<='9')||(s[i]>='a'&&s[i]<='f')))return false;
 return true;
}
void pc_direct_init(pc_direct *d){memset(d,0,sizeof(*d));d->epoch=1;}
void pc_direct_cancel(pc_direct *d){
 unsigned epoch=d->epoch+1;memset(d,0,sizeof(*d));d->epoch=epoch?epoch:1;
}
bool pc_direct_lease(pc_direct *d,const char *lease){
 if(d->running||!hex(lease,64))return false;
 memcpy(d->lease,lease,65);return true;
}
bool pc_direct_claim_ready(const pc_direct *d,bool usb,bool consent,bool ble,bool ota){
 return !d->running&&d->lease[0]&&usb&&consent&&!ble&&!ota;
}
bool pc_direct_begin(pc_direct *d,const char *task,uint64_t now,bool usb,bool consent,bool ble,bool ota){
 if(!hex(task,32)||!pc_direct_claim_ready(d,usb,consent,ble,ota)||now>UINT64_MAX-180000)return false;
 d->running=true;d->until=now+180000;d->count=0;memcpy(d->task,task,33);return true;
}
bool pc_direct_reserve(pc_direct *d,const char *id,uint64_t now,bool usb,bool consent,bool ble,bool ota){
 if(!d->running)return false;
 if(now>=d->until||!usb||!consent||ble||ota){pc_direct_cancel(d);return false;}
 if(!hex(id,32)||d->count>=64)return false;
 for(unsigned i=0;i<d->count;i++)if(!strcmp(d->retired[i],id))return false;
 memcpy(d->retired[d->count++],id,33);return true;
}
