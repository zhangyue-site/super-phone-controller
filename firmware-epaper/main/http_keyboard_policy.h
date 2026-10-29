#pragma once
#include <stddef.h>
#include <stdint.h>
#include <cmath>
#include <cstring>
#include "keyboard_policy.h"
namespace controller {
inline bool keyboard_command_id(const char *id){
 if(!id)return false;
 for(unsigned i=0;i<32;++i){char c=id[i];if(!c||!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return false;}return !id[32];
}
inline bool keyboard_http_text(const char *text,size_t length){
 if(!text||length<1||length>256)return false;
 for(size_t i=0;i<length;++i)if((unsigned char)text[i]<0x20||(unsigned char)text[i]>0x7e)return false;
 return true;
}
inline bool keyboard_json_zero_escape(const char *raw){
 if(!raw)return true;
 for(size_t i=0;raw[i];){
  if(raw[i]!='\\'){++i;continue;}
  size_t slashes=0;while(raw[i]=='\\'){++slashes;++i;}
  if((slashes&1)&&!std::strncmp(raw+i,"u0000",5))return true;
 }
 return false;
}
inline bool keyboard_http_byte(double value){return std::isfinite(value)&&value>=0&&value<=255&&std::floor(value)==value;}
template<class Step,class Live,class Status>
inline bool keyboard_http_run(const char *text,size_t length,Step step,Live live,Status status){
 if(!keyboard_http_text(text,length))return false;
 for(size_t offset=0;offset<length;offset+=8){
  size_t n=length-offset;if(n>8)n=8;
  if(!live()||!status()||!live()||!step((const uint8_t*)text+offset,n))return false;
 }
 return live();
}
}
