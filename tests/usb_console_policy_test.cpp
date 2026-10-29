#include "usb_console_policy.h"
#include "usb_proof_parse.h"
#include <cassert>
#include <cstring>
#include <cstdio>
int main(){
 bool seen=false;
 assert(!controller::usb_download_line_state(false,false,false,true,seen)&&!seen);
 assert(!controller::usb_download_line_state(false,false,true,false,seen)&&!seen);
 assert(!controller::usb_download_line_state(true,false,false,true,seen)&&seen);
 assert(controller::usb_download_line_state(true,false,true,false,seen)&&!seen);
 seen=true;assert(!controller::usb_download_line_state(false,false,true,false,seen)&&!seen);
 seen=true;assert(!controller::usb_download_line_state(true,true,true,false,seen)&&!seen);
 unsigned proofs=0,stops=0,writes=0,denied=0;uint8_t challenge[32]={};
 auto dispatch=[&](char *line,bool maintenance){controller::usb_console_dispatch(line,maintenance,
  [&](char *text){char id[33];++proofs;pc_usb_parse(text,id,challenge);},[&](){++stops;},[&](char*){++writes;},[&](){++denied;});};
 char info[]="PCUSB 0123456789abcdef0123456789abcdef INFO";dispatch(info,false);assert(proofs==1&&writes==0&&denied==0);
 char auth[109];snprintf(auth,sizeof(auth),"PCUSB 0123456789abcdef0123456789abcdef AUTH %064d",0);dispatch(auth,false);assert(proofs==2&&challenge[31]==0&&writes==0);
 auth[107]='1';dispatch(auth,false);assert(proofs==3&&challenge[31]==1&&writes==0); // New challenge is actually parsed, not a cached proof input.
 auth[107]='x';dispatch(auth,false);assert(proofs==4&&writes==0&&denied==0); // Invalid proof frame cannot fall through to CLI.
 const char *commands[]={"MAINT HID ON","MAINT CLICK 1 2","BOOTLOADER","REBOOT","WIFI ON","WIFI\tssid\tpassword","OTA","VOICE START","AUDIO UP","STATUS"};
 for(const char *text:commands){char line[100];strcpy(line,text);dispatch(line,false);}assert(writes==0&&denied==10);
 char stop[]="STOP";dispatch(stop,false);assert(stops==1&&writes==0);
 char maintenance[]="STATUS";dispatch(maintenance,true);assert(writes==1);
 dispatch(info,true);assert(proofs==5&&writes==1); // Proof never becomes a maintenance command.
 char id[33],domain[128];uint8_t nonce[32];assert(pc_usb_parse(info,id,nonce)==1);assert(pc_usb_domain("example-device","example-serial",domain,sizeof(domain))>0);
 assert(!strcmp(domain,"pcusb-v1\nexample-device\nexample-serial\n"));
}
