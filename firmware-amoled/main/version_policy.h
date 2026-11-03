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

/* Automatic background updates only move forward; explicit maintenance can reinstall. */
static inline bool amoled_release_newer(const char *target,const char *current){
 if(!amoled_release_version_valid(target)||!amoled_release_version_valid(current))return false;
 for(unsigned part=0;part<3;part++){
  unsigned a=0,b=0;
  while(*target>='0'&&*target<='9')a=a*10+(unsigned)(*target++-'0');
  while(*current>='0'&&*current<='9')b=b*10+(unsigned)(*current++-'0');
  if(a!=b)return a>b;
  target++;current++;
 }
 return false;
}
