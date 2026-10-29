#pragma once
#include <stdint.h>
#include <stddef.h>
#include <string.h>
namespace controller {
inline bool ota_parse_decimal(const char *&p,uint64_t &value){
 if(*p<'0'||*p>'9')return false;
 value=0;
 do{unsigned digit=*p-'0';if(value>(UINT64_MAX-digit)/10)return false;value=value*10+digit;++p;}while(*p>='0'&&*p<='9');
 return true;
}
inline bool ota_resume_response(int status,const char *range,int64_t length,uint32_t offset,uint32_t total){
 if(status!=206||!range||offset>=total||length!=int64_t(total-offset)||strncmp(range,"bytes ",6))return false;
 const char *p=range+6;uint64_t begin,end,size;
 return ota_parse_decimal(p,begin)&&*p++=='-'&&ota_parse_decimal(p,end)&&*p++=='/'&&ota_parse_decimal(p,size)&&!*p&&begin==offset&&end==uint64_t(total)-1&&size==total;
}
struct OtaResumePolicy {
 unsigned attempts=0;
 bool take_attempt(bool cancelled,bool total_expired){if(cancelled||total_expired||attempts>=3)return false;++attempts;return true;}
 unsigned delay_ms()const{return attempts==1?250:attempts==2?500:1000;}
};
inline bool ota_receive_window_expired(int64_t now,int64_t last_body,int64_t window_started){
 return now-(last_body>window_started?last_body:window_started)>=15000000;
}
}
