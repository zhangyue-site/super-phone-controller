#include <stdlib.h>
#include <unistd.h>
#include "esp_random.h"
#include <string.h>
#include <errno.h>
#include "lwip/sockets.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_app_desc.h"
#include "esp_heap_caps.h"
#include "cJSON.h"
#include "lvgl.h"
#include "esp_lv_adapter.h"
#include "bsp/esp-bsp.h"
#include "identity.h"
#include "wifi.h"
#include "usb.h"
#include "tcp_console.h"

/* LAN-only remote maintenance console on :10006.
 * Handshake: board sends "PCBOARD1 <serial> <challenge-hex>\n"; client answers
 * "AUTH <hex hmac-sha256(challenge)>\n" using the provisioning secret. */

#define CONSOLE_PORT 10006
#define LINE_MAX 1024

/* One deadline for the entire payload, including a peer that stops reading. */
static int send_all(int fd,const char *buf,size_t n){
 const int64_t deadline=esp_timer_get_time()+3000000;
 size_t sent=0;
 while(sent<n){
  int64_t remaining=deadline-esp_timer_get_time();
  if(remaining<=0)return -1;
  fd_set ws;FD_ZERO(&ws);FD_SET(fd,&ws);
  struct timeval tv={remaining/1000000,remaining%1000000};
  int ready=select(fd+1,NULL,&ws,NULL,&tv);
  if(ready<0&&errno==EINTR)continue;
  if(ready<=0)return -1;
  int w=send(fd,buf+sent,n-sent,MSG_DONTWAIT);
  if(w<0&&(errno==EAGAIN||errno==EWOULDBLOCK||errno==EINTR))continue;
  if(w<=0)return -1;
  sent+=(size_t)w;
 }
 return 0;
}
static void send_text(int fd,const char *s){send_all(fd,s,strlen(s));}

static void hex_encode(const uint8_t *in,size_t n,char *out){
 static const char *digits="0123456789abcdef";
 for(size_t i=0;i<n;i++){out[i*2]=digits[in[i]>>4];out[i*2+1]=digits[in[i]&15];}
 out[n*2]=0;
}
static int hex_decode(const char *in,uint8_t *out,size_t n){
 if(strlen(in)!=n*2)return -1;
 for(size_t i=0;i<n;i++){
  char buf[3]={in[i*2],in[i*2+1],0};char *end=NULL;
  long v=strtol(buf,&end,16);
  if(!end||*end)return -1;
  out[i]=(uint8_t)v;
 }
 return 0;
}
/* Deadline covers every byte, not just the first readable byte. */
static bool read_line_deadline(int fd,char *buf,int cap,int seconds){
 const int64_t deadline=esp_timer_get_time()+(int64_t)seconds*1000000;
 int used=0;
 for(;;){
  int64_t remaining=deadline-esp_timer_get_time();
  if(remaining<=0)return false;
  fd_set rs;FD_ZERO(&rs);FD_SET(fd,&rs);
  struct timeval tv={remaining/1000000,remaining%1000000};
  int ready=select(fd+1,&rs,NULL,NULL,&tv);
  if(ready<0&&errno==EINTR)continue;
  if(ready<=0)return false;
  char c;int n=recv(fd,&c,1,MSG_DONTWAIT);
  if(n<0&&(errno==EAGAIN||errno==EWOULDBLOCK||errno==EINTR))continue;
  if(n<=0)return false;
  if(c=='\n'){buf[used]=0;return true;}
  if(c=='\r')continue;
  if(used+1>=cap)return false;
  buf[used++]=c;
 }
}
static void info_reply(int fd){
 char body[640];
 snprintf(body,sizeof(body),
  "{\"version\":\"%s\",\"serial\":\"%s\",\"usb\":%s,\"armed\":%s,"
  "\"wifiConfigured\":%s,\"wifiConnected\":%s,\"otaStage\":%u,\"autoUpdate\":%s,"
  "\"freeHeap\":%u,\"internalHeap\":%u}\n",
  esp_app_get_description()->version,amoled_identity_serial(),
  amoled_usb_ready()?"true":"false",amoled_usb_armed()?"true":"false",
  amoled_wifi_configured()?"true":"false",amoled_wifi_connected()?"true":"false",
  amoled_wifi_ota_stage(),amoled_wifi_auto_update()?"true":"false",
  (unsigned)esp_get_free_heap_size(),(unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL));
 send_text(fd,body);
}
static void snapshot_reply(int fd){
 if(esp_lv_adapter_lock(250)!=ESP_OK){send_text(fd,"SNAP-BUSY\n");return;}
 lv_obj_t *screen=lv_screen_active();
 lv_draw_buf_t *buf=lv_snapshot_take(screen,LV_COLOR_FORMAT_RGB565);
 esp_lv_adapter_unlock();
 if(!buf){send_text(fd,"SNAP-FAILED\n");return;}
 char head[64];
 snprintf(head,sizeof(head),"SNAP %u %u %u\n",buf->header.w,buf->header.h,(unsigned)(buf->header.stride*buf->header.h));
 send_text(fd,head);
 send_all(fd,(const char*)buf->data,buf->header.stride*buf->header.h);
 lv_draw_buf_destroy(buf);
}
static void serve(int fd){
 char line[LINE_MAX];
 uint8_t challenge[32],mac[32];char mac_hex[65],challenge_hex[65];
 esp_fill_random(challenge,sizeof(challenge));
 hex_encode(challenge,sizeof(challenge),challenge_hex);
 char hello[160];
 snprintf(hello,sizeof(hello),"PCBOARD1 %s %s\n",amoled_identity_serial(),challenge_hex);
 send_text(fd,hello);
 if(!read_line_deadline(fd,line,sizeof(line),10)){send_text(fd,"TIMEOUT\n");return;}
 if(strncmp(line,"AUTH ",5)!=0||hex_decode(line+5,mac,sizeof(mac))!=0){send_text(fd,"AUTH-BAD\n");return;}
 if(!amoled_identity_ready()){send_text(fd,"NOT-PROVISIONED\n");return;}
 if(!amoled_identity_hmac(challenge,sizeof(challenge),mac)){send_text(fd,"AUTH-REJECTED\n");return;}
 send_text(fd,"READY\n");
 for(;;){
  if(!read_line_deadline(fd,line,sizeof(line),300))return;
  if(!strcmp(line,"INFO"))info_reply(fd);
  else if(!strcmp(line,"SNAPSHOT"))snapshot_reply(fd);
  else if(!strcmp(line,"OTA")){
   if(amoled_wifi_ota_request())send_text(fd,"OTA-REQUESTED\n");
   else send_text(fd,"OTA-REJECTED\n");
  }
  else if(!strncmp(line,"WIFI ",5)){
   cJSON *o=cJSON_ParseWithOpts(line+5,NULL,true);bool ok=false;
   if(o){if(!cJSON_GetObjectItem(o,"op"))cJSON_AddStringToObject(o,"op","maintenance.wifi.configure");ok=amoled_wifi_console(o);cJSON_Delete(o);}
   send_text(fd,ok?"WIFI-OK\n":"WIFI-REJECTED\n");
  }
  else if(!strcmp(line,"RESTART")){send_text(fd,"BYE\n");shutdown(fd,SHUT_WR);vTaskDelay(pdMS_TO_TICKS(300));esp_restart();}
  else if(!strcmp(line,"QUIT")){send_text(fd,"BYE\n");return;}
  else send_text(fd,"UNSUPPORTED\n");
 }
}
static void loop(void *unused){
 int listener=socket(AF_INET,SOCK_STREAM,0);
 if(listener<0)return;
 struct sockaddr_in addr={0};
 addr.sin_family=AF_INET;addr.sin_port=htons(CONSOLE_PORT);addr.sin_addr.s_addr=htonl(INADDR_ANY);
 if(bind(listener,(struct sockaddr*)&addr,sizeof(addr))<0){close(listener);return;}
 if(listen(listener,1)<0){close(listener);return;}
 for(;;){
  int fd=accept(listener,NULL,NULL);
  if(fd<0)continue;
  serve(fd);
  close(fd);
 }
}
void amoled_tcp_console_start(void){
 if(xTaskCreate(loop,"tcpc",6144,NULL,3,NULL)!=pdPASS)return;
}
