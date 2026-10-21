#pragma once
#include <cstdio>
#include <cstring>
#include <cctype>
namespace controller {
enum class AdbOp {OBSERVE,HOME,BACK,SETTINGS,TAP,SWIPE,LAUNCH};
struct AdbCommand {AdbOp op;int x=0,y=0,x2=0,y2=0;char component[160]={};};
inline bool adb_command(const AdbCommand &c,char *out,unsigned size){
 if(c.x<0||c.y<0||c.x2<0||c.y2<0||c.x>10000||c.y>10000||c.x2>10000||c.y2>10000)return false;
 if(c.op==AdbOp::LAUNCH){
  unsigned slash=0;
  for(const char *p=c.component;*p;p++){
   if(*p=='/')slash++;
   if(!std::isalnum((unsigned char)*p)&&!strchr("._/$",*p))return false;
  }
  if(slash!=1||!strchr(c.component,'.'))return false;
 }
 int n=-1;
 switch(c.op){
 case AdbOp::LAUNCH:n=snprintf(out,size,"am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -n '%s'",c.component);break;
 case AdbOp::HOME:n=snprintf(out,size,"input keyevent KEYCODE_HOME");break;
 case AdbOp::BACK:n=snprintf(out,size,"input keyevent KEYCODE_BACK");break;
 case AdbOp::SETTINGS:n=snprintf(out,size,"am start -a android.settings.SETTINGS");break;
 case AdbOp::TAP:n=snprintf(out,size,"input tap %d %d",c.x,c.y);break;
 case AdbOp::SWIPE:n=snprintf(out,size,"input swipe %d %d %d %d 500",c.x,c.y,c.x2,c.y2);break;
 default:return false;
 }
 return n>0&&(unsigned)n<size;
}
struct AdbReply {
 char tail[64]={};unsigned used=0;
 bool feed(const char *p,unsigned n){
  for(unsigned i=0;i<n;i++){if(p[i]=='\r'||p[i]=='\n')continue;if(used==63){memmove(tail,tail+1,62);used--;}tail[used++]=p[i];tail[used]=0;}return true;
 }
 bool success()const{const char *m="__PC_EXIT_0__";unsigned n=strlen(m);return used>=n&&!strcmp(tail+used-n,m);}
};
}
