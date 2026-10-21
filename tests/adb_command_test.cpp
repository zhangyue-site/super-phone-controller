#include "adb_command.h"
#include <cassert>
#include <cstring>
int main(){
 using namespace controller;char text[128];
 AdbCommand c{AdbOp::TAP,100,200,0,0};assert(adb_command(c,text,sizeof(text)));assert(!strcmp(text,"input tap 100 200"));
 c.x=-1;assert(!adb_command(c,text,sizeof(text)));c.x=10001;assert(!adb_command(c,text,sizeof(text)));
 c={AdbOp::SWIPE,20,30,40,50};assert(adb_command(c,text,sizeof(text)));assert(strstr(text,"500"));
 c={AdbOp::SETTINGS};assert(adb_command(c,text,sizeof(text)));assert(strstr(text,"android.settings.SETTINGS"));
 c={AdbOp::LAUNCH};strcpy(c.component,"com.example.app/.MainActivity");char launch[320];
 assert(adb_command(c,launch,sizeof(launch)));assert(strstr(launch,"'com.example.app/.MainActivity'"));
 strcpy(c.component,"com.bad/.Activity;reboot");assert(!adb_command(c,launch,sizeof(launch)));
 AdbReply reply;assert(reply.feed("part",4));assert(reply.feed("__PC_EXIT_0__",13));assert(reply.success());
 AdbReply failed;failed.feed("__PC_EXIT_1__",13);assert(!failed.success());
 AdbReply incomplete;incomplete.feed("ok",2);assert(!incomplete.success());
}
