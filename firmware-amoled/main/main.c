#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "esp_log.h"
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
LV_FONT_DECLARE(ui_font);
_Static_assert(LVGL_VERSION_MAJOR==9 && LVGL_VERSION_MINOR==6 && LVGL_VERSION_PATCH==0,"Unexpected LVGL version");
#define MAX_PLUGINS 4
#define MAX_JSON 6144
static nvs_handle_t storage;
static cJSON *plugins;
static int page,selected;
static char notice[160];
static bool refresh;
static int notice_ticks;
static lv_obj_t *root,*link_label;
static const char *str(cJSON *o,const char *key){cJSON *v=cJSON_GetObjectItemCaseSensitive(o,key);return cJSON_IsString(v)?v->valuestring:"";}
static cJSON *current(void){return cJSON_GetArrayItem(plugins,selected);}
static void render(void);
static void reply(cJSON *o){char *s=cJSON_PrintUnformatted(o);if(s){usb_write(s);usb_write("\n");free(s);}cJSON_Delete(o);}
static void status(const char *result){cJSON *o=cJSON_CreateObject();cJSON_AddStringToObject(o,"result",result);cJSON_AddStringToObject(o,"serial",usb_serial());cJSON_AddStringToObject(o,"version",esp_app_get_description()->version);cJSON_AddNumberToObject(o,"page",page);cJSON_AddBoolToObject(o,"usb",usb_ready());cJSON_AddBoolToObject(o,"armed",usb_armed());cJSON_AddBoolToObject(o,"runnerConnected",false);cJSON_AddBoolToObject(o,"sharing",false);cJSON_AddNumberToObject(o,"freeHeap",esp_get_free_heap_size());cJSON_AddItemToObject(o,"plugins",cJSON_Duplicate(plugins,true));reply(o);}
static bool version(const char *s,unsigned v[3]){int end=0;for(const char *c=s;*c;c++)if((*c<'0'||*c>'9')&&*c!='.')return false;if(sscanf(s,"%u.%u.%u%n",v,v+1,v+2,&end)!=3||s[end])return false;for(int i=0;i<3;i++)if(v[i]>65535)return false;return true;}
static int compare(unsigned a[3],unsigned b[3]){for(int i=0;i<3;i++){if(a[i]>b[i])return 1;if(a[i]<b[i])return -1;}return 0;}
static bool valid(cJSON *p){unsigned v[3];const char *id=str(p,"id"),*name=str(p,"name");if(strcmp(str(p,"format"),"phone-controller-plugin")||!cJSON_IsNumber(cJSON_GetObjectItem(p,"apiVersion"))||cJSON_GetObjectItem(p,"apiVersion")->valuedouble!=1||!version(str(p,"version"),v)||!id[0]||strlen(id)>63||!name[0]||strlen(name)>90)return false;for(const char *s=id;*s;s++)if(!((*s>='a'&&*s<='z')||(*s>='0'&&*s<='9')||*s=='.'||*s=='-'||*s=='_'))return false;cJSON *r=cJSON_GetObjectItem(p,"runner");return !strcmp(str(r,"type"),"server-workflow")&&strlen(str(r,"entry"))>0&&strlen(str(r,"entry"))<=96;}
static bool save(cJSON *next){char *s=cJSON_PrintUnformatted(next);if(!s)return false;esp_err_t e=nvs_set_str(storage,"plugins",s);free(s);if(e!=ESP_OK||nvs_commit(storage)!=ESP_OK)return false;cJSON_Delete(plugins);plugins=next;return true;}
static void process(char *line){
 cJSON *o=cJSON_Parse(line);if(!o){status("invalid-json");return;}
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
 else if(!strcmp(op,"snapshot")){if(refresh){render();refresh=false;}lv_draw_buf_t *buf=lv_snapshot_take(root,LV_COLOR_FORMAT_RGB565);if(!buf){status("snapshot-failed");goto done;}cJSON *meta=cJSON_CreateObject();cJSON_AddStringToObject(meta,"result","snapshot");cJSON_AddNumberToObject(meta,"width",buf->header.w);cJSON_AddNumberToObject(meta,"height",buf->header.h);cJSON_AddNumberToObject(meta,"stride",buf->header.stride);cJSON_AddNumberToObject(meta,"bytes",buf->header.stride*buf->header.h);reply(meta);usb_write_bytes(buf->data,buf->header.stride*buf->header.h);lv_draw_buf_destroy(buf);usb_write("\n");}
 else if(!strcmp(op,"maintenance.restart")&&!strcmp(str(o,"device"),usb_serial())&&!usb_armed()){status("restarting");vTaskDelay(pdMS_TO_TICKS(100));esp_restart();}
 else if(!strcmp(op,"maintenance.bootloader")&&!strcmp(str(o,"device"),usb_serial())&&!usb_armed()){status("entering-bootloader");vTaskDelay(pdMS_TO_TICKS(100));REG_SET_BIT(RTC_CNTL_OPTION1_REG,RTC_CNTL_FORCE_DOWNLOAD_BOOT);esp_restart();}
 else status("unsupported-operation");
 done:cJSON_Delete(o);
}
static lv_obj_t *label(lv_obj_t *parent,const char *text,int x,int y,int w,lv_color_t color){lv_obj_t *o=lv_label_create(parent);lv_label_set_text(o,text);lv_obj_set_pos(o,x,y);lv_obj_set_width(o,w);lv_obj_set_style_text_font(o,&ui_font,0);lv_obj_set_style_text_color(o,color,0);lv_label_set_long_mode(o,LV_LABEL_LONG_WRAP);return o;}
static void action(lv_event_t *e){int a=(int)(intptr_t)lv_event_get_user_data(e);notice[0]=0;
 if(a>=100&&a<104){selected=a-100;page=2;}
 else if(a==10){page=0;}
 else if(a==11){page=1;}
 else if(a==12){page=3;}
 else if(a==13){page=4;}
 else if(a==14){page=5;}
 else if(a==15){page=6;}
 else if(a==20){usb_gate(false);snprintf(notice,sizeof(notice),"输入已停止，USB连接保留");}
 else if(a==21){if(lv_event_get_code(e)==LV_EVENT_LONG_PRESSED){usb_gate(true);snprintf(notice,sizeof(notice),usb_armed()?"手动输入已开启":"请先连接USB主机");}else return;}
 else if(a>=30&&a<=38){bool ok=false;if(a<=33)ok=usb_mouse(a==30?-24:a==31?24:0,a==32?-24:a==33?24:0,false);else if(a==34)ok=usb_mouse(0,0,true);else ok=usb_consumer(a==35?0x224:a==36?0x223:a==37?0xe9:0xea);snprintf(notice,sizeof(notice),ok?"已提交USB输入，待观察手机":"输入未开启或USB未就绪");}
 else if(a==40){snprintf(notice,sizeof(notice),"106执行器尚未接入，未启动任务");}
 else if(a==41){cJSON *p=current();if(p){cJSON *next=cJSON_Duplicate(plugins,true);cJSON_DeleteItemFromArray(next,selected);if(save(next))page=1;else{cJSON_Delete(next);snprintf(notice,sizeof(notice),"移除失败，原插件保留");}}}
 refresh=true;
}
static void button(const char *text,int x,int y,int w,int h,int a,bool primary){lv_obj_t *b=lv_button_create(root);lv_obj_set_pos(b,x,y);lv_obj_set_size(b,w,h);lv_obj_set_style_radius(b,22,0);lv_obj_set_style_bg_color(b,lv_color_hex(primary?0x14c69b:0x1c1c1c),0);lv_obj_set_style_shadow_width(b,0,0);lv_obj_set_style_border_width(b,0,0);lv_obj_set_style_pad_all(b,6,0);lv_obj_add_event_cb(b,action,a==21?LV_EVENT_LONG_PRESSED:LV_EVENT_CLICKED,(void*)(intptr_t)a);if(a==21)lv_obj_set_style_anim_duration(b,2000,0);lv_obj_t *l=label(b,text,0,0,w-12,lv_color_hex(primary?0:0xf5f5f5));lv_label_set_long_mode(l,LV_LABEL_LONG_DOT);lv_obj_set_height(l,32);lv_obj_set_style_text_align(l,LV_TEXT_ALIGN_CENTER,0);lv_obj_center(l);}
static void render(void){
 lv_obj_clean(root);lv_obj_set_style_bg_color(root,lv_color_black(),0);lv_obj_set_style_pad_all(root,0,0);lv_obj_remove_flag(root,LV_OBJ_FLAG_SCROLLABLE);
 link_label=label(root,usb_ready()?"USB已连接 · 共享未接入":"USB未连接 · 共享未接入",24,20,432,lv_color_hex(0x17baf1));
 const char *titles[]={"手机控制器","我的插件","插件详情","导入插件","手动控制","语音任务","设置"};label(root,titles[page],24,72,432,lv_color_hex(0xf5f5f5));
 if(page==0){button("语音任务",24,124,204,120,14,false);button("插件",252,124,204,120,11,true);button("手动控制",24,268,204,120,13,false);button("设置",252,268,204,120,15,false);}
 else if(page==1){int n=cJSON_GetArraySize(plugins);if(!n){label(root,"尚未导入插件",24,145,432,lv_color_hex(0xf5f5f5));label(root,"业务随插件扩展\n设备保留通用控制能力",24,195,432,lv_color_hex(0xaaaaaa));}if(n){lv_obj_t *list=lv_obj_create(root);lv_obj_set_pos(list,24,112);lv_obj_set_size(list,432,260);lv_obj_set_style_bg_opa(list,0,0);lv_obj_set_style_border_width(list,0,0);lv_obj_set_style_pad_all(list,0,0);lv_obj_t *saved=root;root=list;for(int i=0;i<n;i++)button(str(cJSON_GetArrayItem(plugins,i),"name"),0,i*84,432,72,100+i,false);root=saved;}button("导入说明",24,384,204,72,12,true);button("首页",252,384,204,72,10,false);}
 else if(page==2){cJSON *p=current();label(root,p?str(p,"name"):"未选择插件",24,123,432,lv_color_hex(0xf5f5f5));label(root,p?str(p,"version"):"",24,168,432,lv_color_hex(0x17baf1));label(root,"描述文件已保存\n106执行器尚未连接",24,216,432,lv_color_hex(0xaaaaaa));button("开始任务",24,300,432,72,40,true);button("移除插件",24,384,204,72,41,false);button("插件列表",252,384,204,72,11,false);}
 else if(page==3){label(root,"通过USB导入JSON插件\n支持独立更新与移除\n手机导入入口待接入",24,132,432,lv_color_hex(0xaaaaaa));label(root,"API 1 · 最多4个插件\n导入后不会自动运行",24,260,432,lv_color_hex(0x17baf1));button("返回插件",24,384,432,72,11,true);}
 else if(page==4){if(!usb_armed()){label(root,"仅控制当前USB连接的主机\n长按开启，停止后连接保留",24,138,432,lv_color_hex(0xaaaaaa));button("长按2秒开启输入",24,268,432,72,21,true);}else{button("左",24,112,132,72,30,false);button("上",174,112,132,72,32,false);button("右",324,112,132,72,31,false);button("返回",24,202,132,72,35,false);button("点击",174,202,132,72,34,false);button("下",324,202,132,72,33,false);button("音量+",24,292,132,72,37,false);button("主页",174,292,132,72,36,false);button("音量-",324,292,132,72,38,false);}button("停止输入",24,384,204,72,20,false);button("首页",252,384,204,72,10,false);}
 else if(page==5){label(root,"语音服务尚未接入\n当前不会录音或上传",24,150,432,lv_color_hex(0xaaaaaa));button("回到首页",24,384,432,72,10,true);}
 else if(page==6){label(root,"AMOLED 480 × 480\n固件 0.1.0-amoled\n插件持久化已启用\nWi-Fi / 蓝牙默认关闭",24,126,432,lv_color_hex(0xaaaaaa));button("停止输入",24,308,432,72,20,false);button("回到首页",24,384,432,72,10,true);}
 if(notice[0]){notice_ticks=100;lv_obj_t *box=lv_obj_create(root);lv_obj_set_pos(box,24,180);lv_obj_set_size(box,432,120);lv_obj_set_style_bg_color(box,lv_color_hex(0x21332f),0);lv_obj_set_style_border_width(box,0,0);label(box,notice,0,0,384,lv_color_hex(0xf5f5f5));}
 ESP_LOGI("ui","page=%d plugins=%d usb=%d armed=%d",page,cJSON_GetArraySize(plugins),usb_ready(),usb_armed());
}
void app_main(void){
 ESP_LOGI("amoled","BOOT version=%s target=ESP32-S3-Touch-AMOLED-2.16",esp_app_get_description()->version);
 ESP_ERROR_CHECK(nvs_flash_init());ESP_ERROR_CHECK(nvs_open("plugins",NVS_READWRITE,&storage));
 size_t n=0;if(nvs_get_str(storage,"plugins",NULL,&n)==ESP_OK&&n<=MAX_JSON){char *s=malloc(n);if(s){if(nvs_get_str(storage,"plugins",s,&n)==ESP_OK)plugins=cJSON_Parse(s);free(s);}}
 if(!cJSON_IsArray(plugins)){cJSON_Delete(plugins);plugins=cJSON_CreateArray();}
 if(!bsp_display_start()){ESP_LOGE("amoled","display initialization failed");return;}
 bsp_display_lock(-1);root=lv_screen_active();lv_indev_t *in=NULL;while((in=lv_indev_get_next(in)))lv_indev_set_long_press_time(in,2000);render();bsp_display_unlock();
 usb_start();ESP_ERROR_CHECK(esp_ota_mark_app_valid_cancel_rollback());
 ESP_LOGI("amoled","READY display=480x480 touch=enabled usb=CDC+HID persistentPlugins=%d psramFree=%u",cJSON_GetArraySize(plugins),(unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
 static char line[MAX_JSON+128];size_t pos=0;bool overflow=false;int tick=0;bool last_usb=false;
 for(;;){char buf[128];size_t count=usb_read(buf,sizeof(buf));for(size_t i=0;i<count;i++){char c=buf[i];if(c=='\n'){if(!overflow){line[pos]=0;bsp_display_lock(-1);process(line);bsp_display_unlock();}else status("request-too-large");pos=0;overflow=false;}else if(c!='\r'){if(pos+1<sizeof(line))line[pos++]=c;else overflow=true;}}
  if(usb_ready()!=last_usb){last_usb=usb_ready();refresh=true;}
  if(refresh){bsp_display_lock(-1);render();refresh=false;bsp_display_unlock();}
  if(notice_ticks>0&&--notice_ticks==0){notice[0]=0;refresh=true;}
  if(++tick%500==0)ESP_LOGI("amoled","HEALTH heap=%u plugins=%d",(unsigned)esp_get_free_heap_size(),cJSON_GetArraySize(plugins));
  vTaskDelay(pdMS_TO_TICKS(20));
 }
}
