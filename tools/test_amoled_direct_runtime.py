"""Production direct command parser/USB adapter with real cJSON and fake USB."""
from pathlib import Path
import argparse,subprocess,tempfile
root=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument("--cjson-dir",required=True);args=ap.parse_args()
deps=Path(args.cjson_dir)
source=(root/"firmware-amoled/main/direct.c").read_text()
def fn(name):
 start=source.index(name+"(");start=source.rfind("\n",0,start)+1
 brace=source.index("{",start);end=brace+1;depth=1
 while depth:
  depth+=(source[end]=="{")-(source[end]=="}");end+=1
 return source[start:end]
code=r"""
#include "cJSON.h"
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <assert.h>
#include <stdio.h>
static bool current=true,status=true,usb_ok=true;
static unsigned reports,status_calls;
static uint8_t last_op;static uint16_t last_args[5];
static bool live(uint32_t epoch){return current&&epoch==7;}
static bool status_live(unsigned epoch){status_calls++;return status&&live(epoch);}
static bool amoled_usb_execute(uint8_t op,const uint16_t args[5],bool (*check)(uint32_t),uint32_t epoch){
 if(!check(epoch))return false;
 reports++;last_op=op;memcpy(last_args,args,sizeof(last_args));return usb_ok;
}
"""
code+="\n".join(fn(n) for n in ["str","integer","keys","search_target","execute"])
code+=r"""
static bool run(const char *raw){
 cJSON *o=cJSON_Parse(raw);assert(o);const char *output="";
 bool ok=execute(o,7,&output);cJSON_Delete(o);return ok;
}
static const char *target="\"target\":{\"purpose\":\"visible_search\",\"role\":\"search\",\"visible\":true,\"focused\":true,\"password\":false,\"frame\":1}";
int main(void){
 assert(run("{\"op\":\"hid_home\",\"id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"}"));assert(last_op==1);
 reports=0;
 assert(!run("{\"op\":\"hid_home\",\"extra\":true}"));assert(!reports);
 assert(!run("{\"op\":\"hid_home\",\"op\":\"hid_home\"}"));assert(!reports);
 assert(run("{\"op\":\"hid_pointer\",\"kind\":\"click\",\"x\":32767,\"y\":0}"));assert(last_op==3&&last_args[0]==32767);
 assert(!run("{\"op\":\"hid_pointer\",\"kind\":\"click\",\"x\":32768,\"y\":0}"));
 assert(!run("{\"op\":\"hid_pointer\",\"kind\":\"click\",\"x\":1.5,\"y\":0}"));
 assert(!run("{\"op\":\"hid_pointer\",\"kind\":\"click\",\"x\":1,\"y\":0,\"x2\":2}"));
 assert(!run("{\"op\":\"hid_pointer\",\"kind\":\"move\",\"x\":1,\"y\":0}"));
 assert(run("{\"op\":\"hid_pointer\",\"kind\":\"drag\",\"x\":1,\"y\":2,\"x2\":3,\"y2\":4,\"duration_ms\":100}"));assert(last_op==4);
 assert(!run("{\"op\":\"hid_pointer\",\"kind\":\"drag\",\"x\":1,\"y\":2,\"x2\":3,\"y2\":4,\"duration_ms\":99}"));
 char text[1024];snprintf(text,sizeof(text),"{\"op\":\"hid_text\",\"text\":\"abcdefghijklmnopq\",%s}",target);
 reports=status_calls=0;assert(run(text));assert(reports==3&&status_calls==3&&last_op==14&&last_args[0]==1&&last_args[1]=='q');
 status=false;reports=0;assert(!run(text));assert(!reports);status=true;
 usb_ok=false;reports=0;assert(!run(text));assert(reports==1);usb_ok=true;
 assert(!run("{\"op\":\"hid_text\",\"text\":\"abc\"}"));
 snprintf(text,sizeof(text),"{\"op\":\"hid_key\",\"usage\":40,%s}",target);assert(!run(text)); /* Enter rejected */
 snprintf(text,sizeof(text),"{\"op\":\"hid_key\",\"usage\":42,\"modifier\":1,%s}",target);assert(!run(text));
 snprintf(text,sizeof(text),"{\"op\":\"hid_key\",\"usage\":42,\"modifier\":0,%s}",target);assert(run(text));assert(last_op==13&&last_args[1]==42);
 current=false;reports=0;assert(!run(text));assert(!reports);
 puts("Production direct parser: strict fields, pointer bounds, search target/key restrictions, text fragments and STOP passed");
}
"""
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/"test.c").write_text(code)
 subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror","-fsanitize=address,undefined","-I",str(deps),str(p/"test.c"),str(deps/"cJSON.c"),"-lm","-o",str(p/"test")],check=True)
 subprocess.run([str(p/"test")],check=True)

