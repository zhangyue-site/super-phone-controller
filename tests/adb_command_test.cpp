#include "adb_command.h"
#include <cassert>
#include <cstring>
#include <initializer_list>
int main(){
 using namespace controller;char large[4096];AdbCommand t{};strcpy(t.text_b64,"5p2O5rSL");
 assert(adb_command(t,large,sizeof(large)));assert(strstr(large,"ADB_INPUT_B64"));assert(strstr(large,"trap"));
 assert(!strstr(large,"screencap"));assert(!strstr(large,"input tap"));assert(!strstr(large,"input swipe"));assert(!strstr(large,"am start"));
 strcpy(t.text_b64,"a';reboot");assert(!adb_command(t,large,sizeof(large)));t.text_b64[0]=0;assert(!adb_command(t,large,sizeof(large)));
 AdbReply reply;assert(reply.feed("part",4));assert(reply.feed("__PC_EXIT_0__",13));assert(reply.success());AdbReply failed;failed.feed("__PC_EXIT_1__",13);assert(!failed.success());AdbReply incomplete;incomplete.feed("ok",2);assert(!incomplete.success());

 // op names round trip
 for(AdbOp op:{AdbOp::TYPE_TEXT,AdbOp::SCREENCAP,AdbOp::TAP,AdbOp::SWIPE,AdbOp::EXEC}){
  AdbOp back{};assert(adb_op_parse(adb_op_name(op),back));assert(back==op);
 }
 AdbOp ignored{};assert(!adb_op_parse("reboot",ignored));assert(!adb_op_parse("am_start",ignored));assert(!adb_op_parse(nullptr,ignored));

 // screencap: fixed path, size cap, base64 payload
 AdbCommand shot{};shot.op=AdbOp::SCREENCAP;
 assert(adb_command(shot,large,sizeof(large)));
 assert(strstr(large,"f=/data/local/tmp/controller-screen.png"));
 assert(strstr(large,"screencap -p \"$f\""));
 assert(strstr(large,"rm -f \"$f\"")||strstr(large,"rm -f \"$f\""));
 assert(strstr(large,"__PC_SHOT__"));
 assert(strstr(large,"-gt 393216"));
 assert(strstr(large,"base64"));
 assert(!strstr(large,"ADB_INPUT_B64"));
 // No shell metacharacter can be injected: the path is a compile time literal.
 assert(!strstr(large,";reboot"));

 // tap / swipe
 AdbCommand tap{};tap.op=AdbOp::TAP;tap.x=540;tap.y=1200;
 assert(adb_command(tap,large,sizeof(large)));assert(!strcmp(large,"input tap 540 1200"));
 tap.x=-1;assert(!adb_command(tap,large,sizeof(large)));
 tap.x=32768;tap.y=0;assert(!adb_command(tap,large,sizeof(large)));
 AdbCommand swipe{};swipe.op=AdbOp::SWIPE;swipe.x=10;swipe.y=20;swipe.x2=30;swipe.y2=40;swipe.duration_ms=250;
 assert(adb_command(swipe,large,sizeof(large)));assert(!strcmp(large,"input swipe 10 20 30 40 250"));
 swipe.duration_ms=0;assert(!adb_command(swipe,large,sizeof(large)));
 swipe.duration_ms=10001;assert(!adb_command(swipe,large,sizeof(large)));
 swipe.duration_ms=250;swipe.y2=32768;assert(!adb_command(swipe,large,sizeof(large)));
 // tiny caller buffer must never yield a truncated command
 assert(!adb_command(tap,large,16));

 // EXEC whitelist admits exactly the documented forms
 auto exec=[](const char *cmd){AdbCommand c{};c.op=AdbOp::EXEC;strncpy(c.exec_cmd,cmd,sizeof(c.exec_cmd)-1);char out[512];return adb_command(c,out,sizeof(out));};
 assert(adb_exec_allowed("screencap -p"));
 assert(adb_exec_allowed("screencap -p /data/local/tmp/shot.png"));
 assert(adb_exec_allowed("input tap 12 34"));
 assert(adb_exec_allowed("input swipe 1 2 3 4 500"));
 assert(adb_exec_allowed("input keyevent 26"));
 assert(adb_exec_allowed("wm size"));
 assert(adb_exec_allowed("wm density"));
 assert(adb_exec_allowed("settings get secure default_input_method"));
 assert(adb_exec_allowed("settings get global adb_enabled"));
 assert(adb_exec_allowed("dumpsys window displays"));
 assert(adb_exec_allowed("dumpsys window policy"));
 assert(exec("wm size"));
 {AdbCommand c{};c.op=AdbOp::EXEC;strcpy(c.exec_cmd,"input tap 12 34");char out[64];assert(adb_command(c,out,sizeof(out)));assert(!strcmp(out,"input tap 12 34"));}

 // ...and rejects everything else
 const char *bad[]={
  "screencap","rm -rf /","reboot","sh -c id","su","am start -a x","input text hi","input tap 1","input tap 1 2 3",
  "input tap 1 2; reboot","input tap 1 2|id","input tap 1 2&id","input tap 1 2`id`","input tap 1 2$(id)",
  "settings get secure a>b","settings get secure a<b","settings get secure default_input_method;reboot",
  "settings get secure \nreboot","settings get global","settings put global adb_enabled 1",
  "dumpsys window","dumpsys window policy && reboot","dumpsys window sessions","dumpsys activity",
  "wm size 1080x1920","wm  density","input swipe 1 2 3 4","screencap /sdcard/x.png","screencap -p /data/local/tmp/../x",
  "screencap -p /data/local/tmp/x.png;reboot","screencap --help","input keyevent 320",
  " input tap 1 2","input tap 1 2 ","input  tap 1 2","input tap 1 2 #x","input tap 0x10 2","input tap +1 2",
  "","settings get secure ../../x","screencap -p /data/local/tmp/X.PNG"
 };
 for(const char *cmd:bad)assert(!exec(cmd));
 // Over-long EXEC payload is refused rather than truncated.
 char over[200];memset(over,'a',sizeof(over));over[sizeof(over)-1]=0;
 assert(!exec(over));
}
