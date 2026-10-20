#include "adb_local.h"
#include "sdkconfig.h"
#if CONFIG_CONTROLLER_USB_LOCAL
#include "adb_packet.h"
#include "adb_gate.h"
#include "device_adb_keys.h"
#include "usb_network.h"
#include "voice.h"
#include <atomic>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include "lwip/sockets.h"
#include "lwip/inet.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_random.h"
#include "mbedtls/pk.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
using namespace controller;
static AdbGate gate;
static std::atomic<uint64_t> status(0),failure(0);
static int connect_error=0;
static TaskHandle_t worker;
static int fd=-1;
static unsigned active_epoch;
static int64_t deadline;
static bool live(){return gate.active(active_epoch) && controller_usb_net_peer()!=0;}
static void state(uint32_t token,int s){status=((uint64_t)token<<32)|(unsigned)s;controller_voice_changed(false);}
static bool io(void *buffer,size_t len,bool write){
 auto p=(unsigned char*)buffer;size_t done=0;
 while(done<len && live() && esp_timer_get_time()<deadline){
  int n=write?send(fd,p+done,len-done,0):recv(fd,p+done,len-done,0);
  if(n>0){done+=n;continue;}
  if(n==0)return false;
  if(errno!=EAGAIN && errno!=EWOULDBLOCK && errno!=EINTR)return false;
  vTaskDelay(pdMS_TO_TICKS(10));
 }
 return done==len;
}
static bool packet(uint32_t cmd,uint32_t a,uint32_t b,const void *p=nullptr,size_t n=0){
 if(!live() || n>4096)return false;
 auto h=adb_header(cmd,a,b,(const unsigned char*)p,n);
 return io(&h,sizeof(h),true) && (!n || io((void*)p,n,true));
}
static bool receive(AdbHeader &h,unsigned char *p){
 if(!io(&h,sizeof(h),false) || h.magic!=(h.command^0xffffffffu) || h.length>4096)return false;
 if(h.length && !io(p,h.length,false))return false;
 return adb_valid(h,p,h.length);
}
static int random_bytes(void*,unsigned char *out,size_t size){esp_fill_random(out,size);return 0;}
static bool connect_peer(){
 connect_error=ETIMEDOUT;
 fd=socket(AF_INET,SOCK_STREAM,0);if(fd<0){connect_error=errno;return false;}
 timeval timeout={0,100000};setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout));setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&timeout,sizeof(timeout));
 sockaddr_in local={};local.sin_family=AF_INET;inet_pton(AF_INET,"192.168.77.1",&local.sin_addr);
 if(bind(fd,(sockaddr*)&local,sizeof(local))!=0){connect_error=errno;return false;}
 sockaddr_in peer={};peer.sin_family=AF_INET;peer.sin_port=htons(5555);peer.sin_addr.s_addr=controller_usb_net_peer();
 fcntl(fd,F_SETFL,fcntl(fd,F_GETFL,0)|O_NONBLOCK);
 if(connect(fd,(sockaddr*)&peer,sizeof(peer))==0)return true;
 if(errno!=EINPROGRESS){connect_error=errno;return false;}
 while(live() && esp_timer_get_time()<deadline){
  fd_set ready;FD_ZERO(&ready);FD_SET(fd,&ready);timeval wait={0,100000};
  if(select(fd+1,nullptr,&ready,nullptr,&wait)>0){int error=0;socklen_t size=sizeof(error);if(getsockopt(fd,SOL_SOCKET,SO_ERROR,&error,&size)!=0){connect_error=errno;return false;}connect_error=error;return error==0;}
 }
 return false;
}
static bool authenticate(unsigned char *data){
 const char banner[]="host::";
 if(!packet(ADB_CNXN,0x01000000,4096,banner,sizeof(banner)))return false;
 mbedtls_pk_context key;mbedtls_pk_init(&key);
 bool parsed=mbedtls_pk_parse_key(&key,(const unsigned char*)board_adb_private,sizeof(board_adb_private),nullptr,0,random_bytes,nullptr)==0;
 bool signed_once=false,pub_sent=false,ok=false;AdbHeader h;
 while(parsed && receive(h,data)){
  if(h.command==ADB_CNXN){ok=true;break;}
  if(h.command!=ADB_AUTH || h.arg0!=1 || h.length!=20)break;
  if(!signed_once){
   unsigned char signature[256];size_t len=0;
   if(mbedtls_pk_sign(&key,MBEDTLS_MD_SHA1,data,20,signature,sizeof(signature),&len,random_bytes,nullptr)!=0)break;
   signed_once=true;if(!packet(ADB_AUTH,2,0,signature,len))break;
  }else if(!pub_sent){
   pub_sent=true;state(active_epoch,2);
   if(!packet(ADB_AUTH,3,0,board_adb_public,sizeof(board_adb_public)))break;
  }else break;
 }
 mbedtls_pk_free(&key);return ok;
}
static bool shell_probe(unsigned char *data){
 const char command[]="shell:echo __CONTROLLER_ADB_OK__";
 if(!packet(ADB_OPEN,1,0,command,sizeof(command)))return false;
 AdbHeader h;uint32_t remote=0;bool marker=false;size_t matched=0;
 while(receive(h,data)){
  if(h.command==ADB_OKAY && h.arg1==1){remote=h.arg0;continue;}
  if(h.command==ADB_WRTE && h.arg1==1){
   remote=h.arg0;
   // The fixed probe is tiny, but handle a marker split between WRTE packets.
   static const char expected[]="__CONTROLLER_ADB_OK__";
   static constexpr size_t expected_len=sizeof(expected)-1;

   for(size_t i=0;i<h.length;++i){matched=data[i]==expected[matched]?matched+1:(data[i]==expected[0]?1:0);if(matched==expected_len){marker=true;matched=0;}}
   if(!packet(ADB_OKAY,1,remote))return false;
  }else if(h.command==ADB_CLSE && h.arg1==1){packet(ADB_CLSE,1,h.arg0);return marker;}
  else return false;
 }
 return false;
}
static void run(void*){
 unsigned char *data=(unsigned char*)malloc(4096);
 for(;;){
  ulTaskNotifyTake(pdTRUE,portMAX_DELAY);
  active_epoch=gate.ticket();if(!gate.active(active_epoch))continue;
  state(active_epoch,1);
  int64_t lease_deadline=esp_timer_get_time()+10000000;
  while(gate.active(active_epoch) && !controller_usb_net_peer() && esp_timer_get_time()<lease_deadline)vTaskDelay(pdMS_TO_TICKS(100));
  if(!live() || !data){if(gate.finish(active_epoch)){failure=((uint64_t)(active_epoch&~1u)<<32)|1;state(active_epoch&~1u,4);}continue;}
  deadline=esp_timer_get_time()+2000000;
  bool ok=connect_peer();int reason=ok?0:connect_error==ECONNREFUSED?2:connect_error==ETIMEDOUT?3:4;
  if(ok){deadline=esp_timer_get_time()+25000000;ok=authenticate(data);if(!ok)reason=5;
   else{ok=shell_probe(data);if(!ok)reason=6;}
  }
  if(!ok)ESP_LOGW("adb_local","Probe failed phase=%d socket_error=%d; verify direct phone connection",reason,connect_error);
  if(ok && live()){
   state(active_epoch,3);ESP_LOGI("adb_local","Authorized USB-local ADB shell probe succeeded; no phone action executed");
   while(live()){
    unsigned char byte;int n=recv(fd,&byte,1,MSG_PEEK|MSG_DONTWAIT);
    if(n==0 || (n<0 && errno!=EAGAIN && errno!=EWOULDBLOCK && errno!=EINTR))break;
    vTaskDelay(pdMS_TO_TICKS(100));
   }
  }
  if(fd>=0){shutdown(fd,SHUT_RDWR);close(fd);fd=-1;}
  if(gate.finish(active_epoch)){failure=((uint64_t)(active_epoch&~1u)<<32)|(unsigned)(reason?reason:7);state(active_epoch&~1u,5);}
 }
}
void controller_adb_init(){xTaskCreate(run,"usb_local_adb",8192,nullptr,3,&worker);}
uint32_t controller_adb_ticket(){return gate.ticket();}
bool controller_adb_activate(uint32_t consent){
 if(gate.active(consent) && controller_adb_stage()==3)return true;
 if(!worker)return false;
 uint32_t token;if(!gate.activate(consent,token))return false;
 failure=(uint64_t)token<<32;state(token,1);xTaskNotifyGive(worker);
 int64_t end=esp_timer_get_time()+38000000;
 while(gate.active(token) && controller_adb_stage()!=3 && esp_timer_get_time()<end)vTaskDelay(pdMS_TO_TICKS(50));
 return gate.active(token) && controller_adb_stage()==3;
}
void controller_adb_cancel(){uint32_t token=gate.revoke();failure=(uint64_t)token<<32;state(token,0);}
int controller_adb_stage(){
 uint32_t token=gate.ticket();uint64_t snapshot=status.load();
 return (uint32_t)(snapshot>>32)==token?(int)(snapshot&0xffffffffu):((token&1)?1:0);
}
int controller_adb_error(){uint64_t snapshot=failure.load();return (uint32_t)(snapshot>>32)==gate.ticket()?(int)(snapshot&0xffffffffu):0;}

#else
void controller_adb_init(){}
bool controller_adb_activate(uint32_t){return false;}
uint32_t controller_adb_ticket(){return 0;}
void controller_adb_cancel(){}
int controller_adb_stage(){return 0;}
int controller_adb_error(){return 0;}
#endif
