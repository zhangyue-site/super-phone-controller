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
#include "lvgl.h"
#include "bsp/esp-bsp.h"
#include "bsp/display.h"
#include "cJSON.h"
#include "usb.h"
#include "identity.h"
#include "relay.h"
#include "ota_ble.h"
#include "wifi.h"
#include "direct.h"
#include "audio.h"
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
static char notice[160];
static bool refresh;
static int notice_ticks;
static lv_obj_t *root,*link_label,*voice_status_label;
static const char *str(cJSON *o,const char *key){cJSON *v=cJSON_GetObjectItemCaseSensitive(o,key);return cJSON_IsString(v)?v->valuestring:"";}
static cJSON *current(void){return cJSON_GetArrayItem(plugins,selected);}
static void render(void);
static void reply(cJSON *o){char *s=cJSON_PrintUnformatted(o);if(s){amoled_usb_write(s);amoled_usb_write("\n");free(s);}cJSON_Delete(o);}
static void status(const char *result){cJSON *o=cJSON_CreateObject();cJSON_AddStringToObject(o,"result",result);cJSON_AddStringToObject(o,"serial",amoled_usb_serial());cJSON_AddStringToObject(o,"version",esp_app_get_description()->version);cJSON_AddNumberToObject(o,"page",page);cJSON_AddNumberToObject(o,"uptimeMs",esp_timer_get_time()/1000.0);cJSON_AddNumberToObject(o,"resetReason",esp_reset_reason());cJSON_AddNumberToObject(o,"earlyCrashes",boot_recovery.crashes);cJSON_AddBoolToObject(o,"usb",amoled_usb_ready());cJSON_AddBoolToObject(o,"armed",amoled_usb_armed());cJSON_AddBoolToObject(o,"runnerConnected",amoled_relay_online());cJSON_AddBoolToObject(o,"bluetooth",amoled_relay_connected());cJSON_AddBoolToObject(o,"wifiConfigured",amoled_wifi_configured());cJSON_AddBoolToObject(o,"wifiConnected",amoled_wifi_connected());cJSON_AddNumberToObject(o,"wifiOtaStage",amoled_wifi_ota_stage());cJSON_AddBoolToObject(o,"wifiControlSupported",false);cJSON_AddBoolToObject(o,"wifiDirectConnected",amoled_direct_online());cJSON_AddStringToObject(o,"sharingState","check-phone");cJSON_AddNumberToObject(o,"freeHeap",esp_get_free_heap_size());cJSON_AddNumberToObject(o,"freeInternalHeap",heap_caps_get_free_size(MALLOC_CAP_INTERNAL));cJSON_AddNumberToObject(o,"minFreeInternalHeap",heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL));cJSON_AddNumberToObject(o,"largestInternalBlock",heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL));cJSON_AddNumberToObject(o,"mainStackHighWater",uxTaskGetStackHighWaterMark(NULL));cJSON_AddItemToObject(o,"plugins",cJSON_Duplicate(plugins,true));reply(o);}
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
 }else if(!strcmp(op,"view")){cJSON *p=cJSON_GetObjectItem(o,"page");if(cJSON_IsNumber(p)&&p->valueint>=0&&p->valueint<=6){page=p->valueint;refresh=true;status("view-changed");}else status("invalid-page");}
 else if(!strcmp(op,"snapshot")){if(refresh){render();refresh=false;}lv_draw_buf_t *buf=lv_snapshot_take(root,LV_COLOR_FORMAT_RGB565);if(!buf){status("snapshot-failed");goto done;}cJSON *meta=cJSON_CreateObject();cJSON_AddStringToObject(meta,"result","snapshot");cJSON_AddNumberToObject(meta,"width",buf->header.w);cJSON_AddNumberToObject(meta,"height",buf->header.h);cJSON_AddNumberToObject(meta,"stride",buf->header.stride);cJSON_AddNumberToObject(meta,"bytes",buf->header.stride*buf->header.h);reply(meta);amoled_usb_write_bytes(buf->data,buf->header.stride*buf->header.h);lv_draw_buf_destroy(buf);amoled_usb_write("\n");}
 else if(!strcmp(op,"maintenance.restart")&&!strcmp(str(o,"device"),amoled_usb_serial())&&!amoled_usb_armed()&&!amoled_ota_busy()){status("restarting");vTaskDelay(pdMS_TO_TICKS(100));esp_restart();}
 else if(!strcmp(op,"maintenance.bootloader")&&!strcmp(str(o,"device"),amoled_usb_serial())&&!amoled_usb_armed()&&!amoled_ota_busy()){status("entering-bootloader");vTaskDelay(pdMS_TO_TICKS(100));if(amoled_usb_enter_bootloader()!=ESP_OK)status("bootloader-failed");}
 else status("unsupported-operation");
 done:cJSON_Delete(o);
}
static lv_obj_t *label(lv_obj_t *parent,const char *text,int x,int y,int w,lv_color_t color){lv_obj_t *o=lv_label_create(parent);lv_label_set_text(o,text);lv_obj_set_pos(o,x,y);lv_obj_set_width(o,w);lv_obj_set_style_text_font(o,&ui_font,0);lv_obj_set_style_text_color(o,color,0);lv_label_set_long_mode(o,LV_LABEL_LONG_WRAP);return o;}
static void action(lv_event_t *e){if(page==5)amoled_audio_cancel();int a=(int)(intptr_t)lv_event_get_user_data(e);notice[0]=0;
 if(a>=100&&a<104){selected=a-100;page=2;}
 else if(a==10){page=0;}
 else if(a==11){page=1;}
 else if(a==12){page=3;}
 else if(a==13){page=4;}
 else if(a==14){page=5;}
 else if(a==15){page=6;}
 else if(a==20){amoled_relay_cancel();snprintf(notice,sizeof(notice),"输入已停止，USB连接保留");}
 else if(a==23){bool ok=amoled_direct_enable();snprintf(notice,sizeof(notice),ok?"本地许可已开启，等待已确认任务":"Wi-Fi未连接或控制板忙，未开启");}
 else if(a==22){esp_err_t e=amoled_usb_enter_bootloader();snprintf(notice,sizeof(notice),"维护入口错误 0x%x",(unsigned)e);}
 else if(a==21){if(lv_event_get_code(e)==LV_EVENT_LONG_PRESSED){amoled_usb_gate(true);snprintf(notice,sizeof(notice),amoled_usb_armed()?"手动输入已开启":"请先连接USB主机");}else return;}
 else if(a>=30&&a<=38){bool ok=false;if(a<=33)ok=amoled_usb_mouse(a==30?-24:a==31?24:0,a==32?-24:a==33?24:0,false);else if(a==34)ok=amoled_usb_mouse(0,0,true);else ok=amoled_usb_consumer(a==35?0x224:a==36?0x223:a==37?0xe9:0xea);snprintf(notice,sizeof(notice),ok?"已提交USB输入，待观察手机":"输入未开启或USB未就绪");}
 else if(a==40){snprintf(notice,sizeof(notice),"106执行器尚未接入，未启动任务");}
 else if(a==41){cJSON *p=current();if(p){cJSON *next=cJSON_Duplicate(plugins,true);cJSON_DeleteItemFromArray(next,selected);if(save(next))page=1;else{cJSON_Delete(next);snprintf(notice,sizeof(notice),"移除失败，原插件保留");}}}
 refresh=true;
}
static void button(const char *text,int x,int y,int w,int h,int a,bool primary){lv_obj_t *b=lv_button_create(root);lv_obj_set_pos(b,x,y);lv_obj_set_size(b,w,h);lv_obj_set_style_radius(b,22,0);lv_obj_set_style_bg_color(b,lv_color_hex(primary?0x14c69b:0x1c1c1c),0);lv_obj_set_style_shadow_width(b,0,0);lv_obj_set_style_border_width(b,0,0);lv_obj_set_style_pad_all(b,6,0);lv_obj_add_event_cb(b,action,(a==21||a==22||a==23)?LV_EVENT_LONG_PRESSED:LV_EVENT_CLICKED,(void*)(intptr_t)a);if(a==21)lv_obj_set_style_anim_duration(b,2000,0);lv_obj_t *l=label(b,text,0,0,w-12,lv_color_hex(primary?0:0xf5f5f5));lv_label_set_long_mode(l,LV_LABEL_LONG_DOT);lv_obj_set_height(l,46);lv_obj_set_style_text_align(l,LV_TEXT_ALIGN_CENTER,0);lv_obj_center(l);}
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
static const char *link_status(void){
 if(!amoled_usb_ready())return "USB未连";
 if(amoled_direct_online())return "USB已连 · Wi-Fi任务中";
 if(amoled_relay_online())return "USB已连 · 中转在线";
 if(amoled_relay_connected())return "USB已连 · 蓝牙已连";
 return amoled_identity_ready()?"USB已连 · 等待手机":"USB已连 · 等待配置";
}
static void render(void){
 voice_status_label=NULL;lv_obj_clean(root);lv_obj_set_style_bg_color(root,lv_color_black(),0);lv_obj_set_style_pad_all(root,0,0);lv_obj_remove_flag(root,LV_OBJ_FLAG_SCROLLABLE);
 link_label=label(root,link_status(),80,36,320,lv_color_hex(0x17baf1));lv_obj_set_style_text_align(link_label,LV_TEXT_ALIGN_CENTER,0);
 const char *titles[]={"手机控制器","我的插件","插件详情","导入插件","手动控制","语音任务","设置"};lv_obj_t *title=label(root,titles[page],72,88,336,lv_color_hex(0xf5f5f5));lv_obj_set_style_text_align(title,LV_TEXT_ALIGN_CENTER,0);
 if(page==0){button("语音任务",56,144,176,96,14,false);button("插件",248,144,176,96,11,true);button("手动控制",56,260,176,96,13,false);button("设置",248,260,176,96,15,false);}
 else if(page==1){int n=cJSON_GetArraySize(plugins);if(!n){label(root,"尚未导入插件",88,168,304,lv_color_hex(0xf5f5f5));label(root,"业务随插件扩展\n保留通用控制能力",88,224,304,lv_color_hex(0xaaaaaa));}if(n){lv_obj_t *list=lv_obj_create(root);lv_obj_set_pos(list,64,136);lv_obj_set_size(list,352,232);lv_obj_set_style_bg_opa(list,0,0);lv_obj_set_style_border_width(list,0,0);lv_obj_set_style_pad_all(list,0,0);lv_obj_t *saved=root;root=list;for(int i=0;i<n;i++)button(str(cJSON_GetArrayItem(plugins,i),"name"),0,i*76,352,64,100+i,false);root=saved;}button("导入说明",112,386,120,56,12,true);button("首页",248,386,120,56,10,false);}
 else if(page==2){cJSON *p=current();label(root,p?str(p,"name"):"未选择插件",80,140,320,lv_color_hex(0xf5f5f5));label(root,p?str(p,"version"):"",80,186,320,lv_color_hex(0x17baf1));label(root,"描述文件已保存\n执行器尚未连接",80,232,320,lv_color_hex(0xaaaaaa));button("开始任务",80,318,320,56,40,true);button("移除插件",112,386,120,56,41,false);button("插件列表",248,386,120,56,11,false);}
 else if(page==3){label(root,"通过USB导入JSON插件\n支持独立更新与移除\n手机导入待接入",80,144,320,lv_color_hex(0xaaaaaa));label(root,"API 1 · 最多4个插件\n导入后不会自动运行",80,288,320,lv_color_hex(0x17baf1));button("返回插件",112,386,256,56,11,true);}
 else if(page==4){if(!amoled_usb_armed()){label(root,"控制当前USB主机\n长按开启输入\n停止后连接保留",80,154,320,lv_color_hex(0xaaaaaa));button("长按2秒开启输入",72,310,336,56,21,true);}else{button("左",60,144,104,64,30,false);button("上",188,144,104,64,32,false);button("右",316,144,104,64,31,false);button("返回",60,220,104,64,35,false);button("点击",188,220,104,64,34,false);button("下",316,220,104,64,33,false);button("音量+",60,296,104,64,37,false);button("主页",188,296,104,64,36,false);button("音量-",316,296,104,64,38,false);}button("停止输入",112,386,120,56,20,false);button("首页",248,386,120,56,10,false);}
 else if(page==5){lv_obj_t *voice_box=lv_obj_create(root);lv_obj_set_pos(voice_box,80,136);lv_obj_set_size(voice_box,320,120);lv_obj_set_style_pad_all(voice_box,0,0);lv_obj_set_style_border_width(voice_box,0,0);voice_status_label=label(voice_box,"仅按住时录音，最长10秒\n本次仅识别，不执行手机任务",0,0,300,lv_color_hex(0xaaaaaa));voice_button();button("回到首页",112,386,256,56,10,true);}
 else if(page==6){label(root,amoled_wifi_connected()?"蓝牙手机中转\nWi-Fi已连接 · USB维护升级":amoled_wifi_configured()?"蓝牙手机中转\nWi-Fi尚未连接":"蓝牙手机中转\nWi-Fi未配置",80,144,320,lv_color_hex(0xaaaaaa));button("停止输入",80,250,152,56,20,false);button("长按直连",248,250,152,56,23,true);button("长按2秒进入维护",80,318,320,56,22,false);button("回到首页",112,386,256,56,10,true);}
 if(notice[0]){notice_ticks=100;lv_obj_t *box=lv_obj_create(root);lv_obj_set_pos(box,72,180);lv_obj_set_size(box,336,120);lv_obj_set_style_bg_color(box,lv_color_hex(0x21332f),0);lv_obj_set_style_border_width(box,0,0);label(box,notice,0,0,288,lv_color_hex(0xf5f5f5));}
 ESP_LOGI("ui","page=%d plugins=%d usb=%d armed=%d",page,cJSON_GetArraySize(plugins),amoled_usb_ready(),amoled_usb_armed());
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
 if(!bsp_display_start()){
  ESP_LOGE("amoled","display initialization failed");
  esp_ota_img_states_t failed_state=ESP_OTA_IMG_UNDEFINED;esp_ota_get_state_partition(esp_ota_get_running_partition(),&failed_state);
  if(failed_state==ESP_OTA_IMG_PENDING_VERIFY){esp_ota_mark_app_invalid_rollback_and_reboot();esp_restart();}
  return;
 }
 boot_recovery.stage=4;
 bsp_display_lock(-1);root=lv_screen_active();lv_indev_t *in=NULL;while((in=lv_indev_get_next(in)))lv_indev_set_long_press_time(in,2000);render();bsp_display_unlock();
 snprintf(notice,sizeof(notice),"正在启动USB");bsp_display_lock(-1);render();bsp_display_unlock();
 boot_recovery.stage=5;
 esp_err_t amoled_usb_error=amoled_usb_start();if(amoled_usb_error!=ESP_OK){page=6;snprintf(notice,sizeof(notice),"USB启动失败 0x%x",(unsigned)amoled_usb_error);}else{notice[0]=0;}
 bsp_display_lock(-1);render();bsp_display_unlock();
 boot_recovery.stage=6;
 ESP_LOGI("amoled","READY display=480x480 touch=enabled usb=CDC+HID persistentPlugins=%d psramFree=%u",cJSON_GetArraySize(plugins),(unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
 static char line[MAX_JSON+128];size_t pos=0;bool overflow=false;int tick=0;bool last_usb=false,last_ble=false,last_relay=false,last_direct=false;
 boot_recovery.stage=7;
 esp_err_t relay_error=ESP_ERR_INVALID_STATE;
 if(amoled_identity_ready()){relay_error=amoled_relay_start();if(relay_error!=ESP_OK)ESP_LOGE("amoled","BLE startup failed: %s",esp_err_to_name(relay_error));}
 esp_err_t wifi_error=amoled_wifi_start();if(wifi_error!=ESP_OK)ESP_LOGE("amoled","Wi-Fi startup unavailable: %s",esp_err_to_name(wifi_error));
 esp_ota_img_states_t image_state=ESP_OTA_IMG_UNDEFINED;esp_ota_get_state_partition(esp_ota_get_running_partition(),&image_state);
 bool boot_pending=image_state==ESP_OTA_IMG_PENDING_VERIFY;
 int64_t healthy_since=esp_timer_get_time();
 for(;;){
  if(boot_pending&&esp_timer_get_time()-healthy_since>=30000000){
   if(amoled_usb_error==ESP_OK&&relay_error==ESP_OK&&amoled_relay_ready()&&heap_caps_get_free_size(MALLOC_CAP_INTERNAL)>=32768){
    esp_err_t health=esp_ota_mark_app_valid_cancel_rollback();if(health==ESP_OK)boot_pending=false;else ESP_LOGE("amoled","boot confirmation failed: %s",esp_err_to_name(health));
   }else{ESP_LOGE("amoled","pending image failed startup health; rolling back");esp_ota_mark_app_invalid_rollback_and_reboot();}
  }
  char buf[128];size_t count=amoled_usb_read(buf,sizeof(buf));for(size_t i=0;i<count;i++){char c=buf[i];if(c=='\n'){if(!overflow){line[pos]=0;if(!amoled_control_console(line)){bsp_display_lock(-1);process(line);bsp_display_unlock();}memset(line,0,sizeof(line));}else status("request-too-large");pos=0;overflow=false;}else if(c!='\r'){if(pos+1<sizeof(line))line[pos++]=c;else overflow=true;}}
  if(amoled_usb_ready()!=last_usb||amoled_relay_connected()!=last_ble||amoled_relay_online()!=last_relay||amoled_direct_online()!=last_direct){last_direct=amoled_direct_online();last_usb=amoled_usb_ready();last_ble=amoled_relay_connected();last_relay=amoled_relay_online();refresh=true;}
  if(refresh){bsp_display_lock(-1);render();refresh=false;bsp_display_unlock();}
  if(voice_status_label){
   unsigned stage=amoled_audio_stage();char text[640],recognized[481];
   const char *states[]={"仅按住时录音，最长10秒\n本次仅识别，不执行手机任务","正在录音","正在上传语音","语音识别已返回，未执行任务","未识别：录音过短、静音或上传失败","语音已停止"};
   snprintf(text,sizeof(text),"%s%s%u%s",states[stage<6?stage:4],stage==1?" · ":"",stage==1?amoled_audio_duration_ms():0,stage==1?"毫秒":"");
   if(stage!=1)snprintf(text,sizeof(text),"%s",states[stage<6?stage:4]);
   if(stage==3&&amoled_audio_result(recognized,sizeof(recognized)))snprintf(text,sizeof(text),"识别文字：%s\n未执行手机任务",recognized);
   bsp_display_lock(-1);if(voice_status_label)lv_label_set_text(voice_status_label,text);bsp_display_unlock();
  }
  if(notice_ticks>0&&--notice_ticks==0){notice[0]=0;refresh=true;}
  if(boot_recovery.crashes&&amoled_boot_healthy((uint64_t)esp_timer_get_time()/1000))boot_recovery.crashes=0;
  if(++tick%500==0)ESP_LOGI("amoled","HEALTH heap=%u plugins=%d",(unsigned)esp_get_free_heap_size(),cJSON_GetArraySize(plugins));
  vTaskDelay(pdMS_TO_TICKS(20));
 }
}
