#pragma once
// Shell command construction for the USB-local ADB bridge.
//
// Every op is rendered into a single toybox sh line that is executed by the
// phone's adbd (shell:<line>; echo __PC_EXIT_$?__). All user supplied values are
// either base64 (TYPE_TEXT) or strictly validated integers / whitelisted
// literal tokens, so no user byte ever reaches the shell unquoted.
#include <cstdio>
#include <cstring>
#include <cctype>
namespace controller {
enum class AdbOp {TYPE_TEXT,SCREENCAP,TAP,SWIPE,EXEC};

// Screenshot budget. The PNG is written to /data/local/tmp, its byte size is
// printed as one header line and the file is then dumped as base64 on stdout.
// Base64 costs 4/3 of the PNG plus ~1.3% newline padding, and adb_local keeps a
// 786433 byte reply buffer (command_output in SPIRAM), so 393216 bytes of PNG
// (~533 KB base64) always fits. A 1200x2608 screenshot is typically ~300 KB.
static constexpr int adb_screencap_max_png=393216;
static constexpr unsigned adb_screencap_capacity=560000; // header + base64 + marker
static constexpr const char *adb_screencap_path="/data/local/tmp/controller-screen.png";

struct AdbCommand {
 AdbOp op=AdbOp::TYPE_TEXT;
 char text_b64[513]={};
 int x=0,y=0,x2=0,y2=0,duration_ms=0;
 char exec_cmd[161]={};
};

inline bool adb_op_parse(const char *name,AdbOp &out){
 if(!name)return false;
 if(!std::strcmp(name,"type_text")){out=AdbOp::TYPE_TEXT;return true;}
 if(!std::strcmp(name,"screencap")){out=AdbOp::SCREENCAP;return true;}
 if(!std::strcmp(name,"tap")){out=AdbOp::TAP;return true;}
 if(!std::strcmp(name,"swipe")){out=AdbOp::SWIPE;return true;}
 if(!std::strcmp(name,"exec")){out=AdbOp::EXEC;return true;}
 return false;
}
inline const char *adb_op_name(AdbOp op){
 switch(op){
 case AdbOp::TYPE_TEXT:return "type_text";
 case AdbOp::SCREENCAP:return "screencap";
 case AdbOp::TAP:return "tap";
 case AdbOp::SWIPE:return "swipe";
 case AdbOp::EXEC:return "exec";
 }
 return "unknown";
}
// Decimal only, no sign, no leading '+', bounded. Rejects anything that would
// make the renderer emit a non numeric token.
inline bool adb_number(int value,int max){return value>=0 && value<=max;}
inline bool adb_number_text(const char *p,unsigned len,int &out,int max){
 if(!len||len>5)return false;
 int v=0;
 for(unsigned i=0;i<len;i++){if(p[i]<'0'||p[i]>'9')return false;v=v*10+(p[i]-'0');if(v>max)return false;}
 out=v;return true;
}
// "0.0.0.0"-style keys and package-ish names only.
inline bool adb_token_ok(const char *p,unsigned len,unsigned max){
 if(!len||len>max)return false;
 for(unsigned i=0;i<len;i++){
  char c=p[i];
  if(!((c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='.'||c=='_'||c=='-'))return false;
 }
 return true;
}
// dumpsys window is only allowed in its three read-only summary forms.
inline bool adb_dumpsys_form(const char *p,unsigned len){
 static const char *forms[]={"displays","policy","windows"};
 for(const char *f:forms)if(std::strlen(f)==len&&!std::memcmp(f,p,len))return true;
 return false;
}
// The EXEC whitelist. Grammar (single spaces, no quoting, no metacharacters):
//   screencap [-p] [/data/local/tmp/<name>.png]
//   input tap <x> <y>
//   input swipe <x1> <y1> <x2> <y2> <ms>
//   input keyevent <0..319>
//   wm size | wm density
//   settings get (system|secure|global) <key>
//   dumpsys window (displays|policy|windows)
// Metacharacters are unreachable because the character set is limited to
// [a-z0-9._/-] and single spaces, and the token grammar is matched exactly.
inline bool adb_exec_allowed(const char *command){
 if(!command)return false;
 unsigned len=(unsigned)std::strlen(command);
 if(!len||len>160)return false;
 if(command[0]==' '||command[len-1]==' ')return false;
 const char *token[16];unsigned token_len[16],count=0;
 unsigned i=0;
 while(i<len){
  unsigned start=i;
  while(i<len&&command[i]!=' ')i++;
  if(i==start)return false; // double space
  if(count==16)return false;
  for(unsigned k=start;k<i;k++){
   char c=command[k];
   if(!((c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='.'||c=='_'||c=='-'||c=='/'))return false;
  }
  token[count]=command+start;token_len[count]=i-start;count++;
  if(i<len)i++; // skip single space
 }
 auto is=[&](unsigned n,const char *s){return token_len[n]==std::strlen(s)&&!std::memcmp(token[n],s,token_len[n]);};
 auto num=[&](unsigned n,int max){int v=0;if(!adb_number_text(token[n],token_len[n],v,max))return false;return v>=0;};
 if(is(0,"screencap")){
  // screencap -p / screencap -p <path>. A bare "screencap" dumps raw RGBA
  // (~12 MB for 1200x2608) and would overflow the reply buffer, so it is refused.
  if(count==1)return false;
  if(!is(1,"-p"))return false;
  if(count==2)return true;
  if(count!=3)return false;
  static const char *prefix="/data/local/tmp/";
  const unsigned plen=(unsigned)std::strlen(prefix);
  if(token_len[2]<=plen||std::memcmp(token[2],prefix,plen))return false;
  return adb_token_ok(token[2]+plen,token_len[2]-plen,48);
 }
 if(is(0,"input")){
  if(count>=2&&is(1,"tap"))return count==4&&num(2,32767)&&num(3,32767);
  if(count>=2&&is(1,"swipe"))return count==7&&num(2,32767)&&num(3,32767)&&num(4,32767)&&num(5,32767)&&num(6,10000);
  if(count>=2&&is(1,"keyevent"))return count==3&&num(2,319);
  return false;
 }
 if(is(0,"wm"))return count==2&&(is(1,"size")||is(1,"density"));
 if(is(0,"settings")){
  if(count!=4||!is(1,"get"))return false;
  if(!(is(2,"system")||is(2,"secure")||is(2,"global")))return false;
  return adb_token_ok(token[3],token_len[3],48);
 }
 if(is(0,"dumpsys"))return count==3&&is(1,"window")&&adb_dumpsys_form(token[2],token_len[2]);
 return false;
}
inline bool adb_command(const AdbCommand &c,char *out,unsigned size){
 if(!out||size<64)return false;
 int n=0;
 switch(c.op){
 case AdbOp::TYPE_TEXT:{
  size_t n64=std::strlen(c.text_b64);if(!n64||n64>512||n64%4)return false;
  for(size_t i=0;i<n64;i++)if(!std::isalnum((unsigned char)c.text_b64[i])&&!std::strchr("+/=",c.text_b64[i]))return false;
  n=snprintf(out,size,
   "umask 077; restore_file=/data/local/tmp/controller-ime.restore; "
   "original=$(settings get secure default_input_method); "
   "case \"$original\" in ''|*[!a-zA-Z0-9_./$]*) exit 40;; esac; "
   "test ! -e \"$restore_file\" || exit 41; "
   "printf '%%s' \"$original\" > \"$restore_file\" || exit 42; "
   "restore(){ ime set \"$original\" >/dev/null && sleep 1 && rm -f \"$restore_file\"; }; "
   "trap restore EXIT; trap 'exit 130' HUP INT TERM; "
   "ime set com.android.adbkeyboard/.AdbIME >/dev/null || exit 43; sleep 1; "
   "am broadcast -a ADB_CLEAR_TEXT >/dev/null || exit 44; sleep 1; "
   "am broadcast -a ADB_INPUT_B64 --es msg '%s' >/dev/null || exit 44; sleep 1; "
   "trap - EXIT; restore || exit 45",c.text_b64);
  break;
 }
 case AdbOp::SCREENCAP:
  // Exit codes: 50 screencap failed, 51 unreadable size, 52 PNG over the
  // base64/reply budget (screencap_max_png). The header line lets the caller
  // report the exact PNG size without decoding the payload.
  n=snprintf(out,size,
   "umask 077; f=%s; rm -f \"$f\"; screencap -p \"$f\" || exit 50; "
   "s=$(wc -c < \"$f\"); case \"$s\" in ''|*[!0-9]*) exit 51;; esac; "
   "if [ \"$s\" -gt %d ]; then rm -f \"$f\"; echo __PC_SHOT_TOO_LARGE__ \"$s\"; exit 52; fi; "
   "echo \"__PC_SHOT__ $s\"; base64 \"$f\" || toybox base64 \"$f\"",adb_screencap_path,adb_screencap_max_png);
  break;
 case AdbOp::TAP:
  if(!adb_number(c.x,32767)||!adb_number(c.y,32767))return false;
  n=snprintf(out,size,"input tap %d %d",c.x,c.y);
  break;
 case AdbOp::SWIPE:
  if(!adb_number(c.x,32767)||!adb_number(c.y,32767)||!adb_number(c.x2,32767)||!adb_number(c.y2,32767))return false;
  if(c.duration_ms<1||c.duration_ms>10000)return false;
  n=snprintf(out,size,"input swipe %d %d %d %d %d",c.x,c.y,c.x2,c.y2,c.duration_ms);
  break;
 case AdbOp::EXEC:
  if(!adb_exec_allowed(c.exec_cmd))return false;
  n=snprintf(out,size,"%s",c.exec_cmd);
  break;
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
