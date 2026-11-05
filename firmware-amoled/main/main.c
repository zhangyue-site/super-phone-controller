#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <stdatomic.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#include "esp_app_desc.h"
#include "esp_ota_ops.h"
#include "esp_heap_caps.h"
#include "driver/gpio.h"
#include "lvgl.h"
#include "bsp/esp-bsp.h"
#include "bsp/display.h"
#include "cJSON.h"
#include "usb.h"
#include "tcp_console.h"
#include "identity.h"
#include "relay.h"
#include "ota_ble.h"
#include "wifi.h"
#include "direct.h"
#include "power.h"
#include "audio.h"
#include "plugin.h"
#include "esp_attr.h"
#include "esp_private/panic_internal.h"
#include "boot_recovery_policy.h"
LV_FONT_DECLARE(ui_font);
_Static_assert(LVGL_VERSION_MAJOR==9 && LVGL_VERSION_MINOR==6 && LVGL_VERSION_PATCH==0,"Unexpected LVGL version");
#define MAX_PLUGINS 4
#define MAX_JSON 6144
RTC_NOINIT_ATTR static volatile struct {uint32_t magic,crashes,stage,log_size;char log[4096];uint32_t panic_magic,core,exception,pc;uint32_t frame[32];char reason[128],details[256];} boot_recovery;
// No allocation, locks, logging or flash-resident helpers on the panic path.
void __real_esp_panic_handler(panic_info_t *info);
static void IRAM_ATTR retain_text(volatile char *dst,const char *src,unsigned capacity){unsigned i=0;if(src){for(;i+1<capacity&&src[i];i++)dst[i]=src[i];}dst[i]=0;}
void IRAM_ATTR __wrap_esp_panic_handler(panic_info_t *info){
 boot_recovery.panic_magic=0x50414e31;boot_recovery.core=info->core;boot_recovery.exception=info->exception;boot_recovery.pc=(uint32_t)info->addr;
 retain_text(boot_recovery.reason,info->reason,sizeof(boot_recovery.reason));
 retain_text(boot_recovery.details,g_panic_abort_details?g_panic_abort_details:info->description,sizeof(boot_recovery.details));
 if(info->frame){const uint32_t *f=info->frame;for(unsigned i=0;i<32;i++)boot_recovery.frame[i]=f[i];}
 __real_esp_panic_handler(info);
}
static vprintf_like_t uart_log;
static atomic_flag log_busy=ATOMIC_FLAG_INIT;
static int retained_log(const char *format,va_list args){
 if(!atomic_flag_test_and_set(&log_busy)){
  char text[256];va_list copy;va_copy(copy,args);int n=vsnprintf(text,sizeof(text),format,copy);va_end(copy);
  if(n>0){size_t count=n<(int)sizeof(text)?n:sizeof(text)-1;for(size_t i=0;i<count;i++){uint32_t k=boot_recovery.log_size;boot_recovery.log[k%sizeof(boot_recovery.log)]=text[i];boot_recovery.log_size=k+1;}}
  atomic_flag_clear(&log_busy);
 }
 return uart_log?uart_log(format,args):0;
}
static nvs_handle_t storage;
static cJSON *plugins;
static int page,selected;
static char notice[160],check_hint[80];
static bool refresh;
static int notice_ticks;
static atomic_int power_request;
static atomic_int deferred_action; /* LVGL 事件里不做阻塞调用，延迟到主循环执行 */
static atomic_int pending_power;
static int64_t power_started;
static bool shutdown_sent;
static bool power_notice_persistent;
static esp_err_t power_error=ESP_ERR_INVALID_STATE;

static lv_obj_t *root,*link_label,*voice_status_label,*plugin_status_label,*plugin_confirm_button;
static int last_page=-1;static lv_obj_t *state_label,*chip_label[3],*detail_label,*notice_box,*update_label;
static bool pending_link_refresh;static int64_t last_full_render;
static char voice_prev[640],plugin_prev[1024];
static const char *str(cJSON *o,const char *key){cJSON *v=cJSON_GetObjectItemCaseSensitive(o,key);return cJSON_IsString(v)?v->valuestring:"";}
static cJSON *current(void){return cJSON_GetArrayItem(plugins,selected);}
static void render(int64_t lock_wait_us);
static void reply(cJSON *o){char *s=cJSON_PrintUnformatted(o);if(s){amoled_usb_write(s);amoled_usb_write("\n");free(s);}cJSON_Delete(o);}
static void status(const char *result){cJSON *o=cJSON_CreateObject();cJSON_AddStringToObject(o,"result",result);cJSON_AddStringToObject(o,"serial",amoled_usb_serial());cJSON_AddStringToObject(o,"version",esp_app_get_description()->version);cJSON_AddBoolToObject(o,"powerReady",power_error==ESP_OK);cJSON_AddNumberToObject(o,"powerPending",pending_power);cJSON_AddNumberToObject(o,"page",page);cJSON_AddNumberToObject(o,"uptimeMs",esp_timer_get_time()/1000.0);cJSON_AddNumberToObject(o,"resetReason",esp_reset_reason());cJSON_AddNumberToObject(o,"earlyCrashes",boot_recovery.crashes);cJSON_AddBoolToObject(o,"usb",amoled_usb_ready());cJSON_AddBoolToObject(o,"armed",amoled_usb_armed());cJSON_AddBoolToObject(o,"runnerConnected",amoled_relay_online());cJSON_AddBoolToObject(o,"bluetooth",amoled_relay_connected());cJSON_AddBoolToObject(o,"wifiConfigured",amoled_wifi_configured());cJSON_AddBoolToObject(o,"wifiConnected",amoled_wifi_connected());cJSON_AddNumberToObject(o,"wifiOtaStage",amoled_wifi_ota_stage());cJSON_AddNumberToObject(o,"wifiRuntimeError",amoled_wifi_runtime_error());cJSON_AddBoolToObject(o,"autoUpdate",amoled_wifi_auto_update());cJSON_AddNumberToObject(o,"wifiOtaReceived",amoled_wifi_received());cJSON_AddNumberToObject(o,"wifiOtaTotal",amoled_wifi_total());cJSON_AddBoolToObject(o,"wifiControlSupported",false);cJSON_AddBoolToObject(o,"wifiDirectConnected",amoled_direct_online());cJSON_AddStringToObject(o,"sharingState","check-phone");cJSON_AddNumberToObject(o,"freeHeap",esp_get_free_heap_size());cJSON_AddNumberToObject(o,"freeInternalHeap",heap_caps_get_free_size(MALLOC_CAP_INTERNAL));cJSON_AddNumberToObject(o,"minFreeInternalHeap",heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL));cJSON_AddNumberToObject(o,"largestInternalBlock",heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL));cJSON_AddNumberToObject(o,"mainStackHighWater",uxTaskGetStackHighWaterMark(NULL));cJSON_AddItemToObject(o,"plugins",cJSON_Duplicate(plugins,true));reply(o);}
static bool version(const char *s,unsigned v[3]){int end=0;for(const char *c=s;*c;c++)if((*c<'0'||*c>'9')&&*c!='.')return false;if(sscanf(s,"%5u.%5u.%5u%n",v,v+1,v+2,&end)!=3||s[end])return false;for(int i=0;i<3;i++)if(v[i]>65535)return false;return true;}
static int compare(unsigned a[3],unsigned b[3]){for(int i=0;i<3;i++){if(a[i]>b[i])return 1;if(a[i]<b[i])return -1;}return 0;}
static bool valid(cJSON *p){unsigned v[3];const char *id=str(p,"id"),*name=str(p,"name");if(strcmp(str(p,"format"),"phone-controller-plugin")||!cJSON_IsNumber(cJSON_GetObjectItem(p,"apiVersion"))||cJSON_GetObjectItem(p,"apiVersion")->valuedouble!=1||!version(str(p,"version"),v)||!id[0]||strlen(id)>63||!name[0]||strlen(name)>90)return false;for(const char *s=id;*s;s++)if(!((*s>='a'&&*s<='z')||(*s>='0'&&*s<='9')||*s=='.'||*s=='-'||*s=='_'))return false;cJSON *r=cJSON_GetObjectItem(p,"runner");return !strcmp(str(r,"type"),"server-workflow")&&strlen(str(r,"entry"))>0&&strlen(str(r,"entry"))<=96;}
static bool save(cJSON *next){char *s=cJSON_PrintUnformatted(next);if(!s)return false;esp_err_t e=nvs_set_str(storage,"plugins",s);free(s);if(e!=ESP_OK||nvs_commit(storage)!=ESP_OK)return false;cJSON_Delete(plugins);plugins=next;return true;}
static void process(char *line){
 cJSON *o=cJSON_ParseWithOpts(line,NULL,true);if(!o){status("invalid-json");return;}
 if(amoled_wifi_console(o)){cJSON_Delete(o);return;}
 const char *op=str(o,"op");
 if(!strcmp(op,"status")){status("ok");}
 else if(!strcmp(op,"import")){
  cJSON *p=cJSON_GetObjectItem(o,"plugin");if(!valid(p)){status("invalid-plugin");goto done;}
  int found=-1;for(int i=0;i<cJSON_GetArraySize(plugins);i++)if(!strcmp(str(cJSON_GetArrayItem(plugins,i),"id"),str(p,"id")))found=i;
  if(found<0&&cJSON_GetArraySize(plugins)>=MAX_PLUGINS){status("plugin-limit");goto done;}
  if(found>=0){unsigned a[3],b[3];version(str(p,"version"),a);version(str(cJSON_GetArrayItem(plugins,found),"version"),b);int cmp=compare(a,b);if(cmp<=0){status(cmp?"older-version":"already-imported");goto done;}}
  cJSON *next=cJSON_Duplicate(plugins,true),*copy=cJSON_Duplicate(p,true);
  if(found>=0){cJSON *params=cJSON_GetObjectItem(cJSON_GetArrayItem(plugins,found),"parameters");if(params){cJSON_DeleteItemFromObject(copy,"parameters");cJSON_AddItemToObject(copy,"parameters",cJSON_Duplicate(params,true));}cJSON_ReplaceItemInArray(next,found,copy);}else cJSON_AddItemToArray(next,copy);
  char *encoded=cJSON_PrintUnformatted(next);bool fits=encoded&&strlen(encoded)<MAX_JSON;free(encoded);if(!fits||!save(next)){cJSON_Delete(next);status("storage-error");goto done;}
  page=1;refresh=true;status("imported");
 }else if(!strcmp(op,"remove")){
  int found=-1;for(int i=0;i<cJSON_GetArraySize(plugins);i++)if(!strcmp(str(cJSON_GetArrayItem(plugins,i),"id"),str(o,"id")))found=i;
  if(found<0){status("not-found");goto done;}cJSON *next=cJSON_Duplicate(plugins,true);cJSON_DeleteItemFromArray(next,found);if(!save(next)){cJSON_Delete(next);status("storage-error");goto done;}page=1;refresh=true;status("removed");
 }else if(!strcmp(op,"view")){cJSON *p=cJSON_GetObjectItem(o,"page");
  unsigned ota_stage=amoled_wifi_ota_stage();
  if(ota_stage==2||ota_stage==3){snprintf(notice,sizeof(notice),"固件升级中，请勿断开电源");refresh=true;status("view-deferred");}
  else if(cJSON_IsNumber(p)&&p->valueint>=0&&p->valueint<=10){page=p->valueint;refresh=true;status("view-changed");}else status("invalid-page");}
 else if(!strcmp(op,"snapshot")){if(refresh){render(0);refresh=false;}lv_draw_buf_t *buf=lv_snapshot_take(root,LV_COLOR_FORMAT_RGB565);if(!buf){status("snapshot-failed");goto done;}cJSON *meta=cJSON_CreateObject();cJSON_AddStringToObject(meta,"result","snapshot");cJSON_AddNumberToObject(meta,"width",buf->header.w);cJSON_AddNumberToObject(meta,"height",buf->header.h);cJSON_AddNumberToObject(meta,"stride",buf->header.stride);cJSON_AddNumberToObject(meta,"bytes",buf->header.stride*buf->header.h);reply(meta);amoled_usb_write_bytes(buf->data,buf->header.stride*buf->header.h);lv_draw_buf_destroy(buf);amoled_usb_write("\n");}
 else if(!strcmp(op,"logs")){
  static char log_out[sizeof(boot_recovery.log)];
  uint32_t total=boot_recovery.log_size,count=total>sizeof(boot_recovery.log)?sizeof(boot_recovery.log):total;
  if(boot_recovery.magic!=AMOLED_RECOVERY_MAGIC)count=0;
  uint32_t start=total>=sizeof(boot_recovery.log)?(total%sizeof(boot_recovery.log)):0;
  for(uint32_t i=0;i<count;i++)log_out[i]=boot_recovery.log[(start+i)%sizeof(boot_recovery.log)];
  cJSON *meta=cJSON_CreateObject();cJSON_AddStringToObject(meta,"result","logs");cJSON_AddNumberToObject(meta,"bytes",count);cJSON_AddNumberToObject(meta,"total",total);reply(meta);
  if(count)amoled_usb_write_bytes((const uint8_t*)log_out,count);
  amoled_usb_write("\n");}
 else if(!strcmp(op,"maintenance.restart")&&!strcmp(str(o,"device"),amoled_usb_serial())&&!amoled_usb_armed()&&!amoled_ota_busy()){status("restarting");vTaskDelay(pdMS_TO_TICKS(100));esp_restart();}
 else if(!strcmp(op,"maintenance.bootloader")&&!strcmp(str(o,"device"),amoled_usb_serial())&&!amoled_usb_armed()&&!amoled_ota_busy()){status("entering-bootloader");vTaskDelay(pdMS_TO_TICKS(100));if(amoled_usb_enter_bootloader()!=ESP_OK)status("bootloader-failed");}
 else status("unsupported-operation");
 done:cJSON_Delete(o);
}
static lv_obj_t *label(lv_obj_t *parent,const char *text,int x,int y,int w,lv_color_t color){lv_obj_t *o=lv_label_create(parent);lv_label_set_text(o,text);lv_obj_set_pos(o,x,y);lv_obj_set_width(o,w);lv_obj_set_style_text_font(o,&ui_font,0);lv_obj_set_style_text_color(o,color,0);lv_label_set_long_mode(o,LV_LABEL_LONG_WRAP);return o;}
static void action(lv_event_t *e){if(page==5)amoled_audio_cancel();int a=(int)(intptr_t)lv_event_get_user_data(e);ESP_LOGI("ui","action a=%d page=%d",a,page);notice[0]=0;power_notice_persistent=false;if((pending_power||atomic_load(&power_request))&&a!=20){snprintf(notice,sizeof(notice),"正在处理电源请求，请稍候");refresh=true;return;}
 if(atomic_load(&deferred_action)&&(a==23||a==40||a==42)){snprintf(notice,sizeof(notice),"上一操作仍在处理，请稍候");refresh=true;return;}
 if(a>=100&&a<104){selected=a-100;page=2;}
 else if(a==10){page=0;}
 else if(a==11){page=1;}
 else if(a==12){page=3;}
 else if(a==13){page=4;}
 else if(a==14){page=5;}
 else if(a==15){page=6;}
 else if(a==50){page=8;}
 else if(a==51){page=9;}
 else if(a==52){page=10;}
 else if(a==53||a==54){atomic_store(&power_request,a==53?1:2);}
 else if(a==20){amoled_relay_cancel();snprintf(notice,sizeof(notice),"输入已停止，USB连接保留");}
 else if(a==23){atomic_store(&deferred_action,23);snprintf(notice,sizeof(notice),"正在开启直连，请稍候");}
 else if(a==22){esp_err_t e=amoled_usb_enter_bootloader();snprintf(notice,sizeof(notice),"维护入口错误 0x%x",(unsigned)e);}
 else if(a==21){if(lv_event_get_code(e)==LV_EVENT_LONG_PRESSED){amoled_usb_gate(true);snprintf(notice,sizeof(notice),amoled_usb_armed()?"手动输入已开启":"请先连接USB主机");}else return;}
 else if(a>=30&&a<=38){bool ok=false;if(a<=33)ok=amoled_usb_mouse(a==30?-24:a==31?24:0,a==32?-24:a==33?24:0,false);else if(a==34)ok=amoled_usb_mouse(0,0,true);else ok=amoled_usb_consumer(a==35?0x224:a==36?0x223:a==37?0xe9:0xea);snprintf(notice,sizeof(notice),ok?"已提交USB输入，待观察手机":"输入未开启或USB未就绪");}
 else if(a==40){atomic_store(&deferred_action,40);snprintf(notice,sizeof(notice),"正在准备插件计划，请稍候");}
 else if(a==42){atomic_store(&deferred_action,42);snprintf(notice,sizeof(notice),"正在确认执行，请稍候");}
 else if(a==43){amoled_relay_cancel();}
 else if(a==44){page=2;}
 else if(a==41){cJSON *p=current();if(p){cJSON *next=cJSON_Duplicate(plugins,true);cJSON_DeleteItemFromArray(next,selected);if(save(next))page=1;else{cJSON_Delete(next);snprintf(notice,sizeof(notice),"移除失败，原插件保留");}}}
 else if(a==55){check_hint[0]=0;if(!amoled_usb_ready())snprintf(check_hint,sizeof(check_hint),"请先连接 USB");else if(amoled_usb_armed())snprintf(check_hint,sizeof(check_hint),"请先停止输入");else if(amoled_relay_connected())snprintf(check_hint,sizeof(check_hint),"请先断开蓝牙");else if(!amoled_wifi_configured())snprintf(check_hint,sizeof(check_hint),"未配置 Wi-Fi");else if(!amoled_wifi_connected())snprintf(check_hint,sizeof(check_hint),"Wi-Fi 未连接");else if(!amoled_identity_ready())snprintf(check_hint,sizeof(check_hint),"设备身份未就绪");else if(!amoled_wifi_ota_check())snprintf(check_hint,sizeof(check_hint),"暂时无法检测更新");}
 refresh=true;
}
static lv_obj_t *button(const char *text,int x,int y,int w,int h,int a,bool primary){lv_obj_t *b=lv_button_create(root);lv_obj_set_pos(b,x,y);lv_obj_set_size(b,w,h);if(pending_power||atomic_load(&power_request))lv_obj_add_state(b,LV_STATE_DISABLED);lv_obj_set_style_radius(b,22,0);lv_obj_set_style_bg_color(b,lv_color_hex(primary?0x14c69b:0x1c1c1c),0);lv_obj_set_style_shadow_width(b,0,0);lv_obj_set_style_border_width(b,0,0);lv_obj_set_style_pad_all(b,6,0);lv_obj_add_event_cb(b,action,(a==21||a==22||a==23)?LV_EVENT_LONG_PRESSED:LV_EVENT_CLICKED,(void*)(intptr_t)a);if(a==21)lv_obj_set_style_anim_duration(b,2000,0);lv_obj_t *l=label(b,text,0,0,w-12,lv_color_hex(primary?0:0xf5f5f5));lv_label_set_long_mode(l,LV_LABEL_LONG_DOT);lv_obj_set_height(l,46);lv_obj_set_style_text_align(l,LV_TEXT_ALIGN_CENTER,0);lv_obj_center(l);return b;}
static void voice_hold(lv_event_t *e){
 lv_event_code_t code=lv_event_get_code(e);
 if(code==LV_EVENT_PRESSED){
  if(!amoled_audio_press()){snprintf(notice,sizeof(notice),"录音未开启，请检查网络或控制板状态");refresh=true;}
 }else if(code==LV_EVENT_RELEASED)amoled_audio_release();
 else if(code==LV_EVENT_PRESS_LOST||(code==LV_EVENT_DELETE&&amoled_audio_busy()))amoled_audio_cancel();
}
static void voice_button(void){
 lv_obj_t *button=lv_button_create(root);lv_obj_set_pos(button,72,270);lv_obj_set_size(button,336,86);
 lv_obj_add_event_cb(button,voice_hold,LV_EVENT_ALL,NULL);
 lv_obj_t *text=label(button,"按住说话，松手识别",0,0,300,lv_color_hex(0xf5f5f5));lv_obj_center(text);
}
static char link_text_buf[96];
static const char *link_status(void){
 if(amoled_usb_ready()&&amoled_wifi_connected())return "USB已连 · Wi-Fi通";
 if(amoled_usb_ready())return "USB已连 · Wi-Fi断";
 if(amoled_wifi_connected())return "USB未连 · Wi-Fi通";
 return "USB未连 · Wi-Fi断";
}
static const char *link_full(void){
 char ip[16];
 if(amoled_wifi_ip(ip,sizeof ip)){snprintf(link_text_buf,sizeof link_text_buf,"Wi-Fi通 · %s",ip);return link_text_buf;}
 return link_status();
}
static const char *primary_state(void){if(!amoled_usb_ready())return "待连接";unsigned stage=amoled_plugin_stage();if(stage>=1&&stage<=4)return "任务进行中";return amoled_usb_armed()||amoled_relay_online()||amoled_direct_online()?"可操作":"待连接";}
static void keys_init(void){
 gpio_config_t cfg={.pin_bit_mask=(1ULL<<GPIO_NUM_0)|(1ULL<<GPIO_NUM_18),.mode=GPIO_MODE_INPUT,.pull_up_en=GPIO_PULLUP_ENABLE,.pull_down_en=GPIO_PULLDOWN_DISABLE,.intr_type=GPIO_INTR_DISABLE};
 if(gpio_config(&cfg)!=ESP_OK)ESP_LOGW("keys","GPIO setup failed");
}
static void keys_poll(void){
 static int boot_held,user_held;static int64_t boot_at,user_at;
 int64_t now=esp_timer_get_time();
 int boot=gpio_get_level(GPIO_NUM_0)==0,user=gpio_get_level(GPIO_NUM_18)==0;
 if(boot&&!boot_held){boot_held=1;boot_at=now;}
 if(!boot&&boot_held){boot_held=0;if(now-boot_at>=40000&&now-boot_at<800000){page=6;notice[0]=0;refresh=true;ESP_LOGI("keys","BOOT short");}}
 if(user&&!user_held){user_held=1;user_at=now;}
 if(!user&&user_held){user_held=0;if(now-user_at>=40000&&now-user_at<800000){page=0;notice[0]=0;refresh=true;ESP_LOGI("keys","GPIO18 short");}}
 if(amoled_power_take_short_press()){page=8;notice[0]=0;refresh=true;ESP_LOGI("keys","PWR short");}
}
static lv_obj_t *status_chip(lv_obj_t *parent,const char *name,bool ok,int x,int y){lv_obj_t *chip=lv_obj_create(parent);lv_obj_set_pos(chip,x,y);lv_obj_set_size(chip,140,56);lv_obj_set_style_radius(chip,22,0);lv_obj_set_style_bg_color(chip,lv_color_hex(0x1c1c1c),0);lv_obj_set_style_border_width(chip,0,0);lv_obj_set_style_shadow_width(chip,0,0);lv_obj_set_style_pad_all(chip,0,0);char text[64];snprintf(text,sizeof(text),"%s%s",name,ok?"通":"断");lv_obj_t *l=label(chip,text,0,0,132,lv_color_hex(ok?0x7fd99a:0xaaaaaa));lv_obj_center(l);return chip;}
static void stop_bar(void){lv_obj_t *b=lv_button_create(root);lv_obj_set_pos(b,24,352);lv_obj_set_size(b,432,68);if(pending_power||atomic_load(&power_request))lv_obj_add_state(b,LV_STATE_DISABLED);lv_obj_set_style_radius(b,22,0);lv_obj_set_style_bg_color(b,lv_color_hex(0x3B1210),0);lv_obj_set_style_border_width(b,0,0);lv_obj_set_style_shadow_width(b,0,0);lv_obj_set_style_pad_all(b,6,0);lv_obj_add_event_cb(b,action,LV_EVENT_CLICKED,(void*)(intptr_t)20);lv_obj_t *l=label(b,"停止手机操作",0,0,420,lv_color_hex(0xF2B8B5));lv_obj_set_height(l,46);lv_obj_set_style_text_align(l,LV_TEXT_ALIGN_CENTER,0);lv_obj_center(l);}
static const char *update_status_text(void){
 unsigned stage=amoled_wifi_ota_stage();static char buf[96];
 if(stage==1)return "正在检测固件";
 if(stage==2){unsigned got=amoled_wifi_received(),total=amoled_wifi_total();if(total){snprintf(buf,sizeof(buf),"正在下载 %u%%",got*100/total);return buf;}return "正在下载固件";}
 if(stage==3)return "固件已写入，即将重启";
 if(stage==4)return "检测或升级失败，可重试";
 if(stage==5)return "已是最新固件";
 return check_hint[0]?check_hint:"点按检测固件";
}
static void render(int64_t lock_wait_us){
 if(page==last_page&&!notice[0]&&!notice_box){
  if(page==0&&state_label){
   int64_t t0=esp_timer_get_time();char text[64];bool ok;
   lv_label_set_text(state_label,primary_state());
   ok=amoled_usb_ready();snprintf(text,sizeof(text),"USB%s",ok?"通":"断");lv_label_set_text(chip_label[0],text);lv_obj_set_style_text_color(chip_label[0],lv_color_hex(ok?0x7fd99a:0xaaaaaa),0);
   ok=amoled_wifi_connected();snprintf(text,sizeof(text),"Wi-Fi%s",ok?"通":"断");lv_label_set_text(chip_label[1],text);lv_obj_set_style_text_color(chip_label[1],lv_color_hex(ok?0x7fd99a:0xaaaaaa),0);
   ok=amoled_usb_armed();snprintf(text,sizeof(text),"HID%s",ok?"通":"断");lv_label_set_text(chip_label[2],text);lv_obj_set_style_text_color(chip_label[2],lv_color_hex(ok?0x7fd99a:0xaaaaaa),0);
   if(link_label)lv_label_set_text(link_label,link_full());
   ESP_LOGI("ui","render_inplace_us=%lld lock_wait_us=%lld",(long long)(esp_timer_get_time()-t0),(long long)lock_wait_us);return;}
  if(page==6&&detail_label){
   int64_t t0=esp_timer_get_time();char text[256];char ip[16];bool has_ip=amoled_wifi_ip(ip,sizeof ip);snprintf(text,sizeof(text),"USB %s · Wi-Fi %s\n蓝牙%s · 输入%s%s%s",amoled_usb_ready()?"通":"未连",amoled_wifi_connected()?"通":"未连",amoled_relay_connected()?"通":"未连",amoled_usb_armed()?"开启":"未开启",has_ip?"\nIP ":"",has_ip?ip:"");lv_label_set_text(detail_label,text);
   ESP_LOGI("ui","render_inplace_us=%lld lock_wait_us=%lld",(long long)(esp_timer_get_time()-t0),(long long)lock_wait_us);return;}
 }
 int64_t t0=esp_timer_get_time();
 voice_status_label=NULL;plugin_status_label=NULL;plugin_confirm_button=NULL;notice_box=NULL;update_label=NULL;state_label=NULL;detail_label=NULL;chip_label[0]=NULL;chip_label[1]=NULL;chip_label[2]=NULL;voice_prev[0]=0;plugin_prev[0]=0;lv_obj_clean(root);lv_obj_set_style_bg_color(root,lv_color_black(),0);lv_obj_set_style_pad_all(root,0,0);lv_obj_remove_flag(root,LV_OBJ_FLAG_SCROLLABLE);
 /* Physical keys, left to right above the panel: GPIO18, PWR, BOOT. */
 {const char *hints[]={"首页","电源","状态"};for(int i=0;i<3;i++){lv_obj_t *h=label(root,hints[i],8+i*156,4,148,lv_color_hex(0x8a8a8a));lv_obj_set_style_text_align(h,LV_TEXT_ALIGN_CENTER,0);}}
 link_label=label(root,link_full(),80,40,320,lv_color_hex(0x17baf1));lv_obj_set_style_text_align(link_label,LV_TEXT_ALIGN_CENTER,0);
 const char *titles[]={"手机控制器","我的插件","插件详情","导入插件","手动控制","语音任务","设备状态","插件任务","电源","确认重启","确认关机"};if(page){lv_obj_t *title=label(root,titles[page],72,88,336,lv_color_hex(0xf5f5f5));lv_obj_set_style_text_align(title,LV_TEXT_ALIGN_CENTER,0);}
 if(page==0){state_label=label(root,primary_state(),80,88,320,lv_color_hex(0xf5f5f5));lv_obj_set_style_text_align(state_label,LV_TEXT_ALIGN_CENTER,0);chip_label[0]=lv_obj_get_child(status_chip(root,"USB",amoled_usb_ready(),24,148),0);chip_label[1]=lv_obj_get_child(status_chip(root,"Wi-Fi",amoled_wifi_connected(),170,148),0);chip_label[2]=lv_obj_get_child(status_chip(root,"HID",amoled_usb_armed(),316,148),0);button("语音任务",56,216,176,56,14,false);button("插件",248,216,176,56,11,true);button("手动控制",56,282,176,56,13,false);button("设置",248,282,176,56,15,false);stop_bar();}
 else if(page==1){int n=cJSON_GetArraySize(plugins);if(!n){label(root,"尚未导入插件",88,168,304,lv_color_hex(0xf5f5f5));label(root,"业务随插件扩展\n保留通用控制能力",88,224,304,lv_color_hex(0xaaaaaa));}if(n){lv_obj_t *list=lv_obj_create(root);lv_obj_set_pos(list,64,136);lv_obj_set_size(list,352,232);lv_obj_set_style_bg_opa(list,0,0);lv_obj_set_style_border_width(list,0,0);lv_obj_set_style_pad_all(list,0,0);lv_obj_t *saved=root;root=list;for(int i=0;i<n;i++)button(str(cJSON_GetArrayItem(plugins,i),"name"),0,i*76,352,64,100+i,false);root=saved;}button("导入说明",112,386,120,56,12,true);button("首页",248,386,120,56,10,false);}
 else if(page==2){cJSON *p=current();label(root,p?str(p,"name"):"未选择插件",80,140,320,lv_color_hex(0xf5f5f5));label(root,p?str(p,"version"):"",80,186,320,lv_color_hex(0x17baf1));label(root,"描述文件已保存\n执行须私有工作流允许及本地确认",80,232,320,lv_color_hex(0xaaaaaa));button("预览任务计划",80,318,320,56,40,true);button("移除插件",112,386,120,56,41,false);button("插件列表",248,386,120,56,11,false);}
 else if(page==3){label(root,"通过USB导入JSON插件\n支持独立更新与移除\n手机导入待接入",80,144,320,lv_color_hex(0xaaaaaa));label(root,"API 1 · 最多4个插件\n导入后不会自动运行",80,288,320,lv_color_hex(0x17baf1));button("返回插件",112,386,256,56,11,true);}
 else if(page==4){if(!amoled_usb_armed()){label(root,"控制当前USB主机\n长按开启输入\n停止后连接保留",80,154,320,lv_color_hex(0xaaaaaa));button("长按2秒开启输入",72,310,336,56,21,true);}else{button("左",60,144,104,64,30,false);button("上",188,144,104,64,32,false);button("右",316,144,104,64,31,false);button("返回",60,220,104,64,35,false);button("点击",188,220,104,64,34,false);button("下",316,220,104,64,33,false);button("音量+",60,296,104,64,37,false);button("主页",188,296,104,64,36,false);button("音量-",316,296,104,64,38,false);}button("停止输入",112,386,120,56,20,false);button("首页",248,386,120,56,10,false);}
 else if(page==5){lv_obj_t *voice_box=lv_obj_create(root);lv_obj_set_pos(voice_box,80,136);lv_obj_set_size(voice_box,320,120);lv_obj_set_style_pad_all(voice_box,0,0);lv_obj_set_style_border_width(voice_box,0,0);voice_status_label=label(voice_box,"仅按住时录音，最长10秒\n本次仅识别，不执行手机任务",0,0,300,lv_color_hex(0xaaaaaa));voice_button();button("回到首页",112,386,256,56,10,true);}
 else if(page==6){
  char text[256];char ip[16];bool has_ip=amoled_wifi_ip(ip,sizeof ip);snprintf(text,sizeof(text),"USB %s · Wi-Fi %s\n蓝牙%s · 输入%s%s%s",amoled_usb_ready()?"通":"未连",amoled_wifi_connected()?"通":"未连",amoled_relay_connected()?"通":"未连",amoled_usb_armed()?"开启":"未开启",has_ip?"\nIP ":"",has_ip?ip:"");
  detail_label=label(root,text,48,136,384,lv_color_hex(0xaaaaaa));
  lv_obj_t *v=lv_label_create(root);lv_label_set_text(v,esp_app_get_description()->version);lv_obj_set_pos(v,368,100);lv_obj_set_width(v,88);lv_obj_set_height(v,24);lv_obj_set_style_text_font(v,&lv_font_montserrat_16,0);lv_obj_set_style_text_color(v,lv_color_hex(0xaaaaaa),0);lv_obj_set_style_text_align(v,LV_TEXT_ALIGN_CENTER,0);
  button("停止输入",80,238,152,56,20,false);button("长按直连",248,238,152,56,23,true);
  button("长按2秒进入维护",80,302,320,56,22,false);
  button("回到首页",80,366,152,56,10,true);button("电源",248,366,152,56,50,false);
 }
 else if(page==7){
  lv_obj_t *box=lv_obj_create(root);lv_obj_set_pos(box,64,136);lv_obj_set_size(box,352,172);
  plugin_status_label=label(box,"正在读取真实插件状态",0,0,308,lv_color_hex(0xf5f5f5));
  plugin_confirm_button=button("确认执行本次计划",24,318,296,56,42,true);
  button("返回详情",328,318,128,56,44,false);
  lv_obj_t *stop=lv_button_create(root);lv_obj_set_pos(stop,24,382);lv_obj_set_size(stop,432,64);if(pending_power||atomic_load(&power_request))lv_obj_add_state(stop,LV_STATE_DISABLED);lv_obj_set_style_radius(stop,22,0);lv_obj_set_style_bg_color(stop,lv_color_hex(0x3B1210),0);lv_obj_set_style_border_width(stop,0,0);lv_obj_set_style_shadow_width(stop,0,0);lv_obj_set_style_pad_all(stop,6,0);lv_obj_add_event_cb(stop,action,LV_EVENT_CLICKED,(void*)(intptr_t)43);lv_obj_t *stop_label=label(stop,"停止任务",0,0,420,lv_color_hex(0xF2B8B5));lv_obj_set_height(stop_label,46);lv_obj_set_style_text_align(stop_label,LV_TEXT_ALIGN_CENTER,0);lv_obj_center(stop_label);
 }
 else if(page==8){
  char version_text[64];snprintf(version_text,sizeof(version_text),"固件 %s",esp_app_get_description()->version);
  label(root,version_text,80,118,320,lv_color_hex(0x17baf1));
  update_label=label(root,update_status_text(),48,156,384,lv_color_hex(0xaaaaaa));lv_obj_set_style_text_align(update_label,LV_TEXT_ALIGN_CENTER,0);
  button("检测更新",80,196,320,56,55,true);
  button("重新启动",80,264,320,56,51,false);
  button("关机",80,332,320,56,52,false);
  button("返回设置",112,400,256,56,15,true);
 }
 else if(page==9||page==10){
  label(root,page==9?"将停止输入并重新启动":"将停止输入并关闭电源",80,154,320,lv_color_hex(0xf5f5f5));
  label(root,"升级写入会先取消\n切槽提交中请等待",80,222,320,lv_color_hex(0xaaaaaa));
  button(page==9?"确认重启":"确认关机",80,318,320,56,page==9?53:54,true);
  button("取消",112,386,256,56,50,false);
 }

 if(notice[0]){notice_ticks=(pending_power||power_notice_persistent)?0:400;lv_obj_t *box=lv_obj_create(root);notice_box=box;lv_obj_set_pos(box,72,180);lv_obj_set_size(box,336,120);lv_obj_set_style_bg_color(box,lv_color_hex(0x21332f),0);lv_obj_set_style_border_width(box,0,0);label(box,notice,0,0,288,lv_color_hex(0xf5f5f5));}
 ESP_LOGI("ui","page=%d plugins=%d usb=%d armed=%d render_full_us=%lld lock_wait_us=%lld",page,cJSON_GetArraySize(plugins),amoled_usb_ready(),amoled_usb_armed(),(long long)(esp_timer_get_time()-t0),(long long)lock_wait_us);
 last_page=page;pending_link_refresh=false;last_full_render=esp_timer_get_time();
}
static void update_inplace_status(void){
 if(page!=last_page){pending_link_refresh=true;return;}
 if(!link_label)return;
 bsp_display_lock(-1);lv_label_set_text(link_label,link_status());bsp_display_unlock();
}
/* BSP-internal touch init, linked from the BSP library. */
esp_err_t bsp_touch_new(const bsp_display_cfg_t *cfg,esp_lcd_touch_handle_t *ret_touch);
static void amoled_rounder_cb(lv_event_t *e){lv_area_t *area=lv_event_get_param(e);area->x1=(area->x1>>1)<<1;area->y1=(area->y1>>1)<<1;area->x2=((area->x2>>1)<<1)+1;area->y2=((area->y2>>1)<<1)+1;}
/* Display init with small flush chunks: the BSP default flushes 50 rows at once, which needs a 48KB
 * internal DMA bounce that can never allocate once Wi-Fi is up (draws die with ESP_ERR_NO_MEM and the
 * panel freezes on a stale frame). Ten rows keep the bounce at 9.6KB and everything fits. */
static lv_display_t *amoled_display_start(void){
 /* Same touch orientation as Waveshare bsp_display_start(): CST9217 reads
  * swapped and Y-mirrored. Leaving these flags zero maps taps off the widgets. */
 bsp_display_cfg_t cfg={
  .lv_adapter_cfg=ESP_LV_ADAPTER_DEFAULT_CONFIG(),
  .rotation=ESP_LV_ADAPTER_ROTATE_0,
  .tear_avoid_mode=ESP_LV_ADAPTER_TEAR_AVOID_MODE_NONE,
  .touch_flags={.swap_xy=1,.mirror_x=0,.mirror_y=1},
 };
 if(esp_lv_adapter_init(&cfg.lv_adapter_cfg)!=ESP_OK)return NULL;
 const bsp_display_config_t disp_config={.max_transfer_sz=BSP_LCD_H_RES*10*2};
 esp_lcd_panel_handle_t panel_handle=NULL;esp_lcd_panel_io_handle_t io_handle=NULL;
 if(bsp_display_new(&disp_config,&panel_handle,&io_handle)!=ESP_OK)return NULL;
 esp_lv_adapter_display_config_t disp_cfg={.panel=panel_handle,.panel_io=io_handle,
  .profile={.interface=ESP_LV_ADAPTER_PANEL_IF_OTHER,.rotation=cfg.rotation,.hor_res=BSP_LCD_H_RES,.ver_res=BSP_LCD_V_RES,
   .buffer_height=10,.use_psram=true,.enable_ppa_accel=false,.require_double_buffer=true},
  .tear_avoid_mode=cfg.tear_avoid_mode};
 lv_display_t *disp=esp_lv_adapter_register_display(&disp_cfg);if(!disp)return NULL;
 lv_display_add_event_cb(disp,amoled_rounder_cb,LV_EVENT_INVALIDATE_AREA,NULL);
 esp_lcd_touch_handle_t tp=NULL;
 if(bsp_touch_new(&cfg,&tp)!=ESP_OK)return NULL;
 esp_lv_adapter_touch_config_t touch_cfg=ESP_LV_ADAPTER_TOUCH_DEFAULT_CONFIG(disp,tp);
 if(!esp_lv_adapter_register_touch(&touch_cfg))return NULL;
 if(bsp_display_brightness_init()!=ESP_OK)return NULL;
 if(esp_lv_adapter_start()!=ESP_OK)return NULL;
 return disp;
}
void app_main(void){
 esp_reset_reason_t reset=esp_reset_reason();
 bool crash=reset==ESP_RST_PANIC||reset==ESP_RST_TASK_WDT||reset==ESP_RST_INT_WDT||reset==ESP_RST_WDT;
 boot_recovery.crashes=amoled_boot_crashes(boot_recovery.magic==AMOLED_RECOVERY_MAGIC,boot_recovery.crashes,crash);
 boot_recovery.magic=AMOLED_RECOVERY_MAGIC;
 if(amoled_recovery_required(boot_recovery.crashes)){
  ESP_LOGW("amoled","Repeated early crashes; entering hardware download mode");
  esp_err_t e=amoled_usb_enter_bootloader();ESP_LOGE("amoled","Recovery entry failed: %s",esp_err_to_name(e));
 }

 boot_recovery.stage=1;boot_recovery.log_size=0;boot_recovery.panic_magic=0;uart_log=esp_log_set_vprintf(retained_log);
 ESP_LOGI("amoled","BOOT version=%s target=ESP32-S3-Touch-AMOLED-2.16",esp_app_get_description()->version);
 boot_recovery.stage=2;
 ESP_ERROR_CHECK(nvs_flash_init());ESP_ERROR_CHECK(amoled_identity_init());ESP_ERROR_CHECK(nvs_open("plugins",NVS_READWRITE,&storage));
 size_t n=0;if(nvs_get_str(storage,"plugins",NULL,&n)==ESP_OK&&n<=MAX_JSON){char *s=malloc(n);if(s){if(nvs_get_str(storage,"plugins",s,&n)==ESP_OK)plugins=cJSON_Parse(s);free(s);}}
 if(!cJSON_IsArray(plugins)){cJSON_Delete(plugins);plugins=cJSON_CreateArray();}
 boot_recovery.stage=3;
 if(!amoled_display_start()){
  ESP_LOGE("amoled","display initialization failed");
  esp_ota_img_states_t failed_state=ESP_OTA_IMG_UNDEFINED;esp_ota_get_state_partition(esp_ota_get_running_partition(),&failed_state);
  if(failed_state==ESP_OTA_IMG_PENDING_VERIFY){esp_ota_mark_app_invalid_rollback_and_reboot();esp_restart();}
  return;
 }
 boot_recovery.stage=4;
 power_error=amoled_power_init();if(power_error!=ESP_OK)ESP_LOGW("power","PMIC initialization failed: %s",esp_err_to_name(power_error));else amoled_power_arm_key();keys_init();
 bsp_display_lock(-1);root=lv_screen_active();lv_indev_t *in=NULL;while((in=lv_indev_get_next(in)))lv_indev_set_long_press_time(in,2000);render(0);bsp_display_unlock();
 snprintf(notice,sizeof(notice),"正在启动USB");bsp_display_lock(-1);render(0);bsp_display_unlock();
 boot_recovery.stage=5;
 esp_err_t amoled_usb_error=amoled_usb_start();if(amoled_usb_error!=ESP_OK){page=6;snprintf(notice,sizeof(notice),"USB启动失败 0x%x",(unsigned)amoled_usb_error);}else{notice[0]=0;}
 bsp_display_lock(-1);render(0);bsp_display_unlock();
 boot_recovery.stage=6;
 ESP_LOGI("amoled","READY display=480x480 touch=enabled usb=CDC+HID persistentPlugins=%d psramFree=%u",cJSON_GetArraySize(plugins),(unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
 static char line[MAX_JSON+128];size_t pos=0;bool overflow=false;int tick=0;bool last_usb=false,last_wifi=false,last_ble=false,last_relay=false,last_direct=false;
 boot_recovery.stage=7;
 esp_err_t relay_error=ESP_ERR_INVALID_STATE;
 if(amoled_identity_ready()){relay_error=amoled_relay_start();if(relay_error!=ESP_OK)ESP_LOGE("amoled","BLE startup failed: %s",esp_err_to_name(relay_error));}
 /* Wi-Fi start deferred to the main loop: it raced LVGL/BSP init for internal RAM (0.6.15 NO_MEM burst at 3-5s).
  * Up to 3 attempts, 5s apart, so a transient failure no longer leaves the board offline.
  * The TCP console must start only after the first Wi-Fi attempt: its socket() needs the lwip
  * core that esp_netif_init brings up, and starting it earlier deadlocks the whole system. */
 esp_err_t wifi_error=ESP_ERR_INVALID_STATE;unsigned wifi_attempts=0;int wifi_last=0;static bool console_started=false;
 esp_ota_img_states_t image_state=ESP_OTA_IMG_UNDEFINED;esp_ota_get_state_partition(esp_ota_get_running_partition(),&image_state);
 bool boot_pending=image_state==ESP_OTA_IMG_PENDING_VERIFY;
 int64_t healthy_since=esp_timer_get_time();
 for(;;){
  int requested=atomic_exchange(&power_request,0);
  if(requested&&!pending_power){
   if(requested==2&&power_error!=ESP_OK){
    power_notice_persistent=true;snprintf(notice,sizeof(notice),"电源管理不可用，未关机");refresh=true;
   }else if(!amoled_ota_prepare_power()){
    power_notice_persistent=true;snprintf(notice,sizeof(notice),"正在提交升级，请等待重启后再操作");refresh=true;
   }else{
    amoled_relay_cancel();amoled_usb_gate(false);
    pending_power=requested;power_started=esp_timer_get_time();shutdown_sent=false;
    snprintf(notice,sizeof(notice),"正在停止输入与升级写入");refresh=true;
   }
  }
  {int ua=atomic_exchange(&deferred_action,0);
   if(ua==23){bool ok=amoled_direct_enable();snprintf(notice,sizeof(notice),ok?"本地许可已开启，等待已确认任务":"Wi-Fi未连接或控制板忙，未开启");refresh=true;}
   else if(ua==40){cJSON *plugin=current(),*runner=plugin?cJSON_GetObjectItem(plugin,"runner"):NULL,*params=plugin?cJSON_GetObjectItem(plugin,"parameters"):NULL;
    char *encoded=params?cJSON_PrintUnformatted(params):strdup("{}");
    bool ok=encoded&&amoled_plugin_prepare(str(runner,"entry"),encoded);free(encoded);
    if(ok)page=7;else snprintf(notice,sizeof(notice),"插件计划未开启，请检查连接或先停止当前任务");
    refresh=true;}
   else if(ua==42){if(!amoled_plugin_confirm())snprintf(notice,sizeof(notice),"本次确认不可用，请重新预览");refresh=true;}}
  if(wifi_error!=ESP_OK&&wifi_attempts<3&&(wifi_attempts==0||tick-wifi_last>=1000)){
   wifi_attempts++;wifi_last=tick;wifi_error=amoled_wifi_start();
   if(wifi_error==ESP_OK)ESP_LOGI("amoled","Wi-Fi started on attempt %u",wifi_attempts);
   else ESP_LOGW("amoled","Wi-Fi startup attempt %u failed: %s",wifi_attempts,esp_err_to_name(wifi_error));
  }
  if(!console_started&&wifi_attempts>0){console_started=true;amoled_tcp_console_start();}
  if(pending_power){
   if(!shutdown_sent&&amoled_ota_power_idle()){
    if(pending_power==1){esp_restart();}
    else{
     esp_err_t result=amoled_power_shutdown();
     if(result!=ESP_OK){
      amoled_ota_finish_power();pending_power=0;
      power_notice_persistent=true;snprintf(notice,sizeof(notice),"关机请求失败 0x%x",(unsigned)result);refresh=true;
     }else{
      shutdown_sent=true;power_started=esp_timer_get_time();
      snprintf(notice,sizeof(notice),"已请求关机，正在等待电源关闭");refresh=true;
     }
    }
   }else if(esp_timer_get_time()-power_started>10000000){
    amoled_ota_finish_power();pending_power=0;
    power_notice_persistent=true;snprintf(notice,sizeof(notice),shutdown_sent?"设备仍未关机，请检查供电或长按PWR":"停止升级写入超时，设备保持运行");
    refresh=true;
   }
  }
  if(boot_pending){static int64_t last_health_log;if(esp_timer_get_time()-last_health_log>=5000000){last_health_log=esp_timer_get_time();ESP_LOGI("ota","health usb_ok=%d relay_ready=%d wifi=%d heap=%d pending=%d",amoled_usb_error==ESP_OK,amoled_relay_ready(),amoled_wifi_connected(),heap_caps_get_free_size(MALLOC_CAP_INTERNAL),boot_pending);}}
  if(boot_pending&&esp_timer_get_time()-healthy_since>=30000000){
   if(amoled_usb_error==ESP_OK&&(!amoled_wifi_configured()||wifi_error==ESP_OK)&&(amoled_relay_ready()||amoled_wifi_connected())&&heap_caps_get_free_size(MALLOC_CAP_INTERNAL)>=16384){
    esp_err_t health=esp_ota_mark_app_valid_cancel_rollback();if(health==ESP_OK)boot_pending=false;else ESP_LOGE("amoled","boot confirmation failed: %s",esp_err_to_name(health));
   }else{ESP_LOGE("amoled","pending image failed startup health; rolling back");esp_ota_mark_app_invalid_rollback_and_reboot();}
  }
  char buf[128];size_t count=amoled_usb_read(buf,sizeof(buf));for(size_t i=0;i<count;i++){char c=buf[i];if(c=='\n'){if(!overflow){line[pos]=0;if(!amoled_control_console(line)){bsp_display_lock(-1);process(line);bsp_display_unlock();}memset(line,0,sizeof(line));}else status("request-too-large");pos=0;overflow=false;}else if(c!='\r'){if(pos+1<sizeof(line))line[pos++]=c;else overflow=true;}}
  if(amoled_usb_ready()!=last_usb||amoled_wifi_connected()!=last_wifi||amoled_relay_connected()!=last_ble||amoled_relay_online()!=last_relay||amoled_direct_online()!=last_direct){last_direct=amoled_direct_online();last_usb=amoled_usb_ready();last_wifi=amoled_wifi_connected();last_ble=amoled_relay_connected();last_relay=amoled_relay_online();update_inplace_status();refresh=true;}
  if(tick%6000==0){last_page=-1;refresh=true;}
  if(refresh&&esp_timer_get_time()-last_full_render>=200000){int64_t lock_t0=esp_timer_get_time();bsp_display_lock(-1);int64_t lock_wait=esp_timer_get_time()-lock_t0;render(lock_wait);refresh=false;bsp_display_unlock();vTaskDelay(pdMS_TO_TICKS(10));}
  if(plugin_status_label){
   char text[1024];
   if(amoled_plugin_text(text,sizeof(text))){bsp_display_lock(-1);if(plugin_status_label&&strcmp(text,plugin_prev)){lv_label_set_text(plugin_status_label,text);strcpy(plugin_prev,text);}if(plugin_confirm_button){if(amoled_plugin_stage()==1)lv_obj_remove_state(plugin_confirm_button,LV_STATE_DISABLED);else lv_obj_add_state(plugin_confirm_button,LV_STATE_DISABLED);}bsp_display_unlock();}
  }
  if(voice_status_label){
   unsigned stage=amoled_audio_stage();char text[640],recognized[481];
   const char *states[]={"仅按住时录音，最长10秒\n本次仅识别，不执行手机任务","正在录音","正在上传语音","语音识别已返回，未执行任务","未识别：录音过短、静音或上传失败","语音已停止"};
   snprintf(text,sizeof(text),"%s%s%u%s",states[stage<6?stage:4],stage==1?" · ":"",stage==1?amoled_audio_duration_ms():0,stage==1?"毫秒":"");
   if(stage!=1)snprintf(text,sizeof(text),"%s",states[stage<6?stage:4]);
   if(stage==3&&amoled_audio_result(recognized,sizeof(recognized)))snprintf(text,sizeof(text),"识别文字：%s\n未执行手机任务",recognized);
   if(strcmp(text,voice_prev)){bsp_display_lock(-1);if(voice_status_label)lv_label_set_text(voice_status_label,text);bsp_display_unlock();strcpy(voice_prev,text);}
  }
  {static unsigned ota_prev=0;unsigned ota_stage=amoled_wifi_ota_stage();
   char ota_text[160];ota_text[0]=0;
   if(ota_stage==2){unsigned got=amoled_wifi_received(),total=amoled_wifi_total();
    if(total)snprintf(ota_text,sizeof(ota_text),"固件升级中 %u%%，请勿断开电源",got*100/total);
    else snprintf(ota_text,sizeof(ota_text),"固件升级中，请勿断开电源");}
   else if(ota_stage==3)snprintf(ota_text,sizeof(ota_text),"固件已写入，即将重启");
   if(ota_text[0]&&strcmp(notice,ota_text)){snprintf(notice,sizeof(notice),"%s",ota_text);notice_ticks=0;refresh=true;}
   if(ota_prev&&ota_prev<=3&&ota_stage==4){snprintf(notice,sizeof(notice),"升级失败，可重试");notice_ticks=1000;refresh=true;}
   if((ota_stage==0||ota_stage==1)&&ota_prev>=2&&!notice_ticks){notice[0]=0;refresh=true;}
   if(update_label){const char *text=update_status_text();static char shown[96];if(strcmp(shown,text)){snprintf(shown,sizeof(shown),"%s",text);bsp_display_lock(-1);if(update_label)lv_label_set_text(update_label,shown);bsp_display_unlock();}}
   ota_prev=ota_stage;}
  if(notice_ticks>0&&--notice_ticks==0){notice[0]=0;refresh=true;}
  keys_poll();
  if(boot_recovery.crashes&&amoled_boot_healthy((uint64_t)esp_timer_get_time()/1000))boot_recovery.crashes=0;
  if(++tick%2000==0)ESP_LOGI("amoled","HEALTH heap=%u internal=%u min=%u plugins=%d",(unsigned)esp_get_free_heap_size(),(unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),(unsigned)heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL),cJSON_GetArraySize(plugins));
  vTaskDelay(pdMS_TO_TICKS(5));
 }
}
