#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#define PC_RPC_HEADER 22
#define PC_RPC_REQUEST_MAX 2048
#define PC_RPC_RESPONSE_MAX 8192
/* Never evict cancelled IDs during a physical BLE connection. */
typedef struct {uint8_t ids[64][16];unsigned count;} pc_rpc_retired;
static inline bool pc_rpc_is_retired(const pc_rpc_retired *r,const uint8_t *id){
 for(unsigned i=0;i<r->count;i++){if(!memcmp(r->ids[i],id,16))return true;}
 return false;
}
static inline bool pc_rpc_retire(pc_rpc_retired *r,const uint8_t *id){
 if(pc_rpc_is_retired(r,id))return true;
 if(r->count>=64)return false;
 memcpy(r->ids[r->count++],id,16);return true;
}
/* Ordered, single request assembly. Reset on malformed/interleaved input. */
typedef struct {uint8_t id[16];uint16_t used,total;uint8_t data[PC_RPC_REQUEST_MAX+1];} pc_rpc_assembly;
static inline int pc_rpc_push(pc_rpc_assembly *a,const uint8_t *p,size_t n){
 unsigned offset,total,size;
 if(n<=PC_RPC_HEADER || p[0]!=1 || p[1]!=1)goto bad;
 offset=p[18]|(p[19]<<8);total=p[20]|(p[21]<<8);size=n-PC_RPC_HEADER;
 if(!total || total>PC_RPC_REQUEST_MAX || offset!=a->used || offset+size>total)goto bad;
 if(!offset){memcpy(a->id,p+2,16);a->total=total;}
 if(total!=a->total || memcmp(a->id,p+2,16))goto bad;
 memcpy(a->data+offset,p+PC_RPC_HEADER,size);a->used+=size;
 if(a->used==total){a->data[total]=0;return 1;}return 0;
bad:memset(a,0,sizeof(*a));return -1;
}
static inline int pc_rpc_push_guarded(pc_rpc_assembly *a,const pc_rpc_retired *r,const uint8_t *p,size_t n){
 if(n<PC_RPC_HEADER || pc_rpc_is_retired(r,p+2)){memset(a,0,sizeof(*a));return -1;}
 return pc_rpc_push(a,p,n);
}
static inline bool pc_rpc_live(unsigned captured,unsigned current,bool connected,bool permitted){return captured==current && connected && permitted;}
static inline int pc_hex_value(char c){return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:c>='A'&&c<='F'?c-'A'+10:-1;}
static inline bool pc_hex_decode(const char *s,size_t n,uint8_t *out){
 for(size_t i=0;i<n;++i){int a=pc_hex_value(s[2*i]),b=pc_hex_value(s[2*i+1]);if(a<0||b<0)return false;if(out)out[i]=(a<<4)|b;}return true;
}
static inline int pc_usb_parse(const char *line,char *id,uint8_t *challenge){
 size_t n=strlen(line);if(n<43 || strncmp(line,"PCUSB ",6) || line[38]!=' ' || !pc_hex_decode(line+6,16,NULL))return 0;
 int op=strcmp(line+39,"INFO")==0?1:n==108 && !strncmp(line+39,"AUTH ",5) && pc_hex_decode(line+44,32,challenge)?2:0;
 if(op && id){memcpy(id,line+6,32);id[32]=0;}return op;
}

static inline int pc_usb_domain(const char *device,const char *serial,char *out,size_t capacity){
 if(strchr(device,'\n')||strchr(serial,'\n')||strchr(device,'\r')||strchr(serial,'\r'))return -1;
 int n=snprintf(out,capacity,"pcusb-v1\n%s\n%s\n",device,serial);return n>0&&(size_t)n<capacity?n:-1;
}
