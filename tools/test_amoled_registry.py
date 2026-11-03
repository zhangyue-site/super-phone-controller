"""Test the firmware registry C functions, with mocked device I/O and real cJSON.
ASan/UBSan checks are host checks; this does not replace physical board acceptance.
"""
from pathlib import Path
import json,requests,subprocess,base64,re,hashlib,os,shutil,tempfile,argparse
root=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--output-dir');args=ap.parse_args()
out=Path(args.output_dir) if args.output_dir else Path(tempfile.mkdtemp(prefix='amoled-registry-'))
out.mkdir(parents=True,exist_ok=True)
s=requests.Session();s.trust_env=False
token=os.environ.get('GH_TOKEN','')
if not token and shutil.which('gh'):
 auth=subprocess.run(['gh','auth','token'],capture_output=True,text=True)
 if auth.returncode==0:token=auth.stdout.strip()
if token:s.headers['Authorization']='Bearer '+token
for name in ['cJSON.h','cJSON.c']:
 p=out/name
 if not p.exists():
  r=s.get('https://api.github.com/repos/DaveGamble/cJSON/contents/'+name+'?ref=v1.7.19',timeout=15);r.raise_for_status();p.write_bytes(base64.b64decode(r.json()['content']))
source=(root/'firmware-amoled/main/main.c').read_text()
def extract(name):
 m=re.search(r'^static [^\n]*\b'+name+r'\([^\n]*?\)\s*\{',source,re.M);assert m,name
 start=m.start();i=source.find('{',m.start());depth=0;quote=None;escaped=False
 for j in range(i,len(source)):
  c=source[j]
  if quote:
   if escaped:escaped=False
   elif c=='\\':escaped=True
   elif c==quote:quote=None
  elif c in ['"',"'"]:quote=c
  elif c=='{':depth+=1
  elif c=='}':
   depth-=1
   if depth==0:return source[start:j+1]
 raise ValueError(name)
shim=r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <assert.h>
#include "cJSON.h"
#define ESP_OK 0
#define LV_COLOR_FORMAT_RGB565 0
#define RTC_CNTL_OPTION1_REG 0
#define RTC_CNTL_FORCE_DOWNLOAD_BOOT 0
#define REG_SET_BIT(a,b) ((void)0)
#define pdMS_TO_TICKS(a) (a)
typedef int esp_err_t;
static int storage,page;
static bool refresh;
static void *root;
static cJSON *plugins;
static char last[100];
static int fail_set,fail_commit,restarts,bootloader_calls;
static char *saved;
static void status(const char *r){snprintf(last,sizeof(last),"%s",r);}
static void reply(cJSON *o){cJSON_Delete(o);}
static int nvs_set_str(int h,const char *k,const char *v){if(fail_set)return -1;free(saved);saved=strdup(v);return 0;}
static int nvs_commit(int h){return fail_commit?-1:0;}
static void render(void){}
static bool amoled_usb_armed(void){return false;}
/* Registry tests keep unrelated Wi-Fi maintenance in its separately exercised adapter. */
static bool amoled_wifi_console(cJSON *request){return false;}
static bool ota_busy;
static bool amoled_ota_busy(void){return ota_busy;}
static const char *amoled_usb_serial(void){return "host-test-device";}
static void amoled_usb_write(const char *s){}
static void amoled_usb_write_bytes(const void *p,size_t n){}
static void vTaskDelay(int n){}
static void esp_restart(void){restarts++;}
static int amoled_usb_enter_bootloader(void){bootloader_calls++;return 0;}
typedef struct {struct {int w,h,stride;} header;void *data;} lv_draw_buf_t;
static lv_draw_buf_t *lv_snapshot_take(void *p,int fmt){return NULL;}
static void lv_draw_buf_destroy(lv_draw_buf_t *p){}
/* OTA-priority: view deferencing inside process() needs these stubs. */
static char notice[160];
static int notice_ticks;
static int amoled_wifi_runtime_error(void){return 0;}
static unsigned amoled_wifi_ota_stage(void){return ota_busy?3u:0u;}
'''
code='#include "boot_recovery_policy.h"\n'+shim+'\n'+'\n'.join(re.findall(r'^#define MAX_(?:PLUGINS|JSON) .*$',source,re.M))+'\n'
code+='\n'.join(extract(name) for name in ['str','version','compare','valid','save','process'])
cases=json.loads((root/'tests/fixtures/amoled-plugin-cases.json').read_text())
code+='\nint main(void){plugins=cJSON_CreateArray();\n'
for i,c in enumerate(cases):
 req=json.dumps(json.dumps(c['request'],ensure_ascii=False),ensure_ascii=False)
 code+=' {char input[]='+req+';last[0]=0;process(input);if(strcmp(last,'+json.dumps(c['expect'])+')){fprintf(stderr,"case '+c['name']+': %s\\n",last);return '+str(i+1)+';}}\n'
 if c['name']=='upgrade-retain-parameters':code+=' assert(!strcmp(str(cJSON_GetObjectItem(cJSON_GetArrayItem(plugins,0),"parameters"),"until"),"2026-09-10"));\n'
code+='''
assert(cJSON_GetArraySize(plugins)==4);assert(restarts==0);assert(bootloader_calls==0);
ota_busy=true;
char restart_busy[]={"{\\\"op\\\":\\\"maintenance.restart\\\",\\\"device\\\":\\\"host-test-device\\\"}"};
char bootloader_busy[]={"{\\\"op\\\":\\\"maintenance.bootloader\\\",\\\"device\\\":\\\"host-test-device\\\"}"};
process(restart_busy);assert(!strcmp(last,"unsupported-operation")&&restarts==0);process(bootloader_busy);assert(!strcmp(last,"unsupported-operation")&&bootloader_calls==0);ota_busy=false;

assert(amoled_boot_crashes(false,99,true)==1);assert(amoled_boot_crashes(true,1,true)==2);
assert(amoled_boot_crashes(true,2,true)==3);assert(amoled_recovery_required(3));
assert(!amoled_recovery_required(2));assert(amoled_boot_crashes(true,2,false)==0);
assert(amoled_boot_crashes(true,UINT32_MAX,true)==1);
assert(!amoled_boot_healthy(29999));assert(amoled_boot_healthy(30000));
const char *name=str(cJSON_GetArrayItem(plugins,0),"name");assert(name[0]);
unsigned v[3];assert(!version("65536.0.0",v));assert(!version("-1.0.0",v));assert(!version("1.2.3x",v));
assert(!version("4294967296.0.0",v));
char malformed[]={"{"};process(malformed);assert(!strcmp(last,"invalid-json"));
char concatenated[]={"{}{}"};process(concatenated);assert(!strcmp(last,"invalid-json"));
fail_set=1;char rm[]={"\\\"op\\\":\\\"remove\\\""};(void)rm;
char remove_request[]="{\\\"op\\\":\\\"remove\\\",\\\"id\\\":\\\"demo.auto-bookkeeping\\\"}";
process(remove_request);assert(!strcmp(last,"storage-error"));assert(cJSON_GetArraySize(plugins)==4);
fail_set=0;fail_commit=1;process(remove_request);assert(!strcmp(last,"storage-error"));assert(cJSON_GetArraySize(plugins)==4);
fail_commit=0;process(remove_request);assert(!strcmp(last,"removed"));assert(cJSON_GetArraySize(plugins)==3);
cJSON_Delete(plugins);free(saved);puts("registry host checks passed");return 0;}
'''
(out/'registry.c').write_text(code)
r=subprocess.run(['gcc','-g','-O1','-fsanitize=address,undefined','-fno-omit-frame-pointer','-Wno-unused-function','-I'+str(out),'-I'+str(root/'firmware-amoled/main'),str(out/'registry.c'),str(out/'cJSON.c'),'-lm','-o',str(out/'registry-test')],capture_output=True,text=True)
(out/'compile.log').write_text(r.stdout+r.stderr)
if r.returncode:print((r.stdout+r.stderr)[-5000:]);raise SystemExit(r.returncode)
r=subprocess.run([str(out/'registry-test')],capture_output=True,text=True);(out/'result.log').write_text(r.stdout+r.stderr)
print(r.stdout+r.stderr);print('exit',r.returncode)
(out/'proof.json').write_text(json.dumps({'main_source_sha256':hashlib.sha256(source.encode()).hexdigest(),'boot_policy_sha256':hashlib.sha256((root/'firmware-amoled/main/boot_recovery_policy.h').read_bytes()).hexdigest(),'cjson':'v1.7.19','sanitizers':['address','undefined'],'returncode':r.returncode,'hardware_verified':False},indent=2))
raise SystemExit(r.returncode)
