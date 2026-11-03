#pragma once
#include <stdbool.h>
#include <string.h>
/* Ordering is a user-confirmed phone policy. The board still requires a fresh
 * device- and image-bound grant, matching project, full digest and slot bounds. */
static inline bool amoled_release_version_valid(const char *s){
 if(!s)return false;
 for(unsigned part=0;part<3;part++){
  if(*s<'0'||*s>'9')return false;
  bool zero=*s=='0';unsigned digits=0;
  do{if(++digits>5)return false;s++;}while(*s>='0'&&*s<='9');
  if(zero&&digits>1)return false;
  if(part<2){if(*s++!='.')return false;}
 }
 return !strcmp(s,"-amoled");
}
