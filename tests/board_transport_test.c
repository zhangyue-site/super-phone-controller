#include "../firmware-epaper/main/board_transport.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void){
 pc_rpc_retired retired={0}; uint8_t retired_id[16]={7};
 assert(!pc_rpc_is_retired(&retired,retired_id));
 assert(pc_rpc_retire(&retired,retired_id));
 assert(pc_rpc_is_retired(&retired,retired_id));
 /* A delayed one-frame request and final fragment are both fenced by ID. */
 assert(pc_rpc_is_retired(&retired,retired_id));
 for(unsigned i=1;i<64;i++){retired_id[0]=i+7;assert(pc_rpc_retire(&retired,retired_id));}
 retired_id[0]=100;assert(!pc_rpc_retire(&retired,retired_id));
 pc_rpc_assembly late={0};uint8_t old_packet[24]={1,1};memset(old_packet+2,7,16);old_packet[20]=2;
 pc_rpc_retired late_retired={0};
 assert(pc_rpc_retire(&late_retired,old_packet+2));
 assert(pc_rpc_push_guarded(&late,&late_retired,old_packet,24)<0); /* late complete single frame */
 memset(&late_retired,0,sizeof(late_retired));old_packet[20]=4;
 assert(pc_rpc_push_guarded(&late,&late_retired,old_packet,24)==0);
 assert(pc_rpc_retire(&late_retired,old_packet+2));old_packet[18]=2;
 assert(pc_rpc_push_guarded(&late,&late_retired,old_packet,24)<0); /* late final fragment */
 pc_rpc_assembly a={0}; uint8_t p[32]={1,1}; memset(p+2,0x42,16);p[20]=4;
 assert(pc_rpc_push(&a,p,24)==0); assert(a.used==2);
 p[18]=2;assert(pc_rpc_push(&a,p,24)==1);assert(a.used==4);
 assert(pc_rpc_push(&a,p,24)<0); /* replay/nonzero first offset */
 memset(&a,0,sizeof(a));p[18]=0;p[20]=1;p[21]=8;assert(pc_rpc_push(&a,p,24)<0);
 memset(&a,0,sizeof(a));p[20]=4;p[21]=0;assert(pc_rpc_push(&a,p,24)==0);
 p[2]++;p[18]=2;assert(pc_rpc_push(&a,p,24)<0); /* interleaving */
 assert(pc_usb_parse("PCUSB 0123456789abcdef0123456789abcdef INFO",NULL,NULL)==1);
 assert(pc_usb_parse("PCUSB 0123456789abcdef0123456789abcdef AUTH 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",NULL,NULL)==2);
 assert(pc_usb_parse("PCUSB 0123456789abcdef0123456789abcdef INFO extra",NULL,NULL)==0);
 assert(pc_usb_parse("PCUSB 0123456789abcdef0123456789abcdeg INFO",NULL,NULL)==0);
 assert(!pc_rpc_live(7,8,1,1));assert(!pc_rpc_live(7,7,1,0));assert(pc_rpc_live(7,7,1,1));
 char domain[128];assert(pc_usb_domain("board-a","AABB00112233",domain,sizeof(domain))>0);
 assert(!strcmp(domain,"pcusb-v1\nboard-a\nAABB00112233\n"));
 assert(pc_usb_domain("board-a","AABB00112233",domain,4)<0);
 /* Any fragmented maximum request must fit with its trailing NUL. */
 memset(&a,0,sizeof(a));memset(p,0,sizeof(p));p[0]=1;p[1]=1;p[21]=8;
 for(unsigned offset=0;offset<2048;offset+=10){
  unsigned count=2048-offset;if(count>10)count=10;
  p[18]=offset&255;p[19]=offset>>8;
  int result=pc_rpc_push(&a,p,22+count);assert(result==(offset+count==2048?1:0));
 }
 assert(a.used==2048 && a.data[2048]==0);
 /* Malformed packet fuzzing keeps the assembly bounded. */
 unsigned seed=1;
 for(unsigned trial=0;trial<100000;++trial){for(unsigned i=0;i<32;++i){seed=seed*1664525+1013904223;p[i]=seed>>24;}pc_rpc_push(&a,p,trial%33);assert(a.used<=2048);}
 puts("board transport host tests passed");
}
