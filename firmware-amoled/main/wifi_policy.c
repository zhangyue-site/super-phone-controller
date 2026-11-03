#include "wifi_policy.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <ctype.h>
bool pc_wifi_maintenance_allowed(bool usb,bool armed,bool ota,bool ble){return usb&&!armed&&!ota&&!ble;}
bool pc_wifi_config_valid(const char *ssid,const char *password,const char *endpoint){
 if(!ssid||!password||!endpoint||!ssid[0]||strlen(ssid)>32||strlen(password)<8||strlen(password)>63)return false;
 size_t len=strlen(endpoint);
 if(len<9||len>190||strncmp(endpoint,"https://",8)||endpoint[len-1]=='/')return false;
 const char *p=endpoint+8,*host=p;
 while(*p&&*p!='/'&&*p!=':'){if(!(isalnum((unsigned char)*p)||*p=='.'||*p=='-'))return false;p++;}
 if(p==host||host[0]=='-'||host[0]=='.'||p[-1]=='-'||p[-1]=='.')return false;
 if(*p==':'){
  unsigned port=0;p++;const char *start=p;
  while(*p>='0'&&*p<='9'){port=port*10+(unsigned)(*p-'0');if(port>65535)return false;p++;}
  if(p==start||!port)return false;
 }
 if(*p&&*p!='/')return false;
 for(;*p;p++)if(!(isalnum((unsigned char)*p)||*p=='/'||*p=='.'||*p=='-'||*p=='_'))return false;
 return true;
}
bool pc_wifi_manifest(const char *raw,size_t len,uint32_t *size,char sha[65],char version[32]){
 if(!raw||len<80||len>192||memcmp(raw,"PCOTA1\n",7)||raw[len-1]!='\n'||memchr(raw,0,len))return false;
 char text[193];memcpy(text,raw,len);text[len]=0;
 const char *p=text+7;char *end;errno=0;
 if(*p<'1'||*p>'9')return false;
 unsigned long total=strtoul(p,&end,10);
 if(errno||*end!='\n'||total<4096||total>0x600000)return false;
 p=end+1;if(strlen(p)<66)return false;
 for(unsigned i=0;i<64;i++)if(!((p[i]>='0'&&p[i]<='9')||(p[i]>='a'&&p[i]<='f')))return false;
 if(p[64]!='\n')return false;
 memcpy(sha,p,64);sha[64]=0;p+=65;
 size_t vn=strlen(p);if(vn<2||vn>32||p[vn-1]!='\n'||memchr(p,'\n',vn-1))return false;
 memcpy(version,p,vn-1);version[vn-1]=0;*size=(uint32_t)total;return true;
}
