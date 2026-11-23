#include "companion_ui.h"
#include "companion_task.h"
#include "companion_monitor.h"
#include "plugin.h"
#include "pet/pet_assets.h"
#include "esp_timer.h"
LV_FONT_DECLARE(companion_font);
static lv_obj_t *scene,*pet,*headline,*detail,*rows[8],*badges[8],*current_line,*sync_line;
static lv_event_cb_t handler;
static bool disabled,progress_view,has_task,force_home,needs_build;
static int64_t touch_until,last_frame;
static unsigned frame;
static bool was_patted;
static unsigned last_sync;
static pc_companion shown;
static const uint32_t navy=0x141729,cream=0xffe4ba,muted=0xb9bed2,green=0x8cdda7;
static lv_obj_t *text(lv_obj_t *p,const char *value,int x,int y,int w,uint32_t color){
 lv_obj_t *o=lv_label_create(p);lv_label_set_text(o,value);lv_obj_set_pos(o,x,y);lv_obj_set_width(o,w);
 lv_obj_set_style_text_font(o,&companion_font,0);lv_obj_set_style_text_color(o,lv_color_hex(color),0);lv_label_set_long_mode(o,LV_LABEL_LONG_DOT);return o;
}
static void toggle(lv_event_t *e){(void)e;force_home=!force_home;needs_build=true;}
static void pat(lv_event_t *e){(void)e;touch_until=esp_timer_get_time()+3000000;}
static lv_obj_t *button(const char *title,int x,int y,int w,int h,int action,uint32_t bg,uint32_t fg){
 lv_obj_t *o=lv_button_create(scene);lv_obj_set_pos(o,x,y);lv_obj_set_size(o,w,h);lv_obj_set_style_radius(o,22,0);
 lv_obj_set_style_bg_color(o,lv_color_hex(bg),0);lv_obj_set_style_border_width(o,0,0);lv_obj_set_style_shadow_width(o,0,0);lv_obj_set_style_pad_all(o,0,0);
 if(disabled)lv_obj_add_state(o,LV_STATE_DISABLED);
 lv_obj_t *l=text(o,title,0,0,w-12,fg);lv_obj_set_style_text_align(l,LV_TEXT_ALIGN_CENTER,0);lv_obj_center(l);
 if(action>=0)lv_obj_add_event_cb(o,handler,LV_EVENT_CLICKED,(void*)(intptr_t)action);
 return o;
}
static const char *phase_title(pc_phase p){
 static const char *titles[]={"陪着你","正在编排任务","等待执行确认","等待控制板领取","正在识别手机画面","已收到下发指令","正在操作手机","正在核验结果","结果已核验","任务未完成","停止请求已发出","任务已停止","等待任务状态回执"};
 return titles[p<=PC_UNKNOWN?p:PC_UNKNOWN];
}
static const char *home_greeting(void){
 if(shown.phase==PC_DONE)return "办好了，看看结果吧。";
 if(shown.phase==PC_ERROR)return "这次没完成，原因在进度里。";
 if(shown.phase==PC_STOPPED)return "已经停下来了，我在呢。";
 return "我在呢，今天想做点什么？";
}
static void build(void){
 lv_obj_clean(scene);pet=headline=detail=current_line=sync_line=NULL;memset(rows,0,sizeof(rows));memset(badges,0,sizeof(badges));
 lv_obj_set_style_bg_color(scene,lv_color_hex(navy),0);
 /* Keep all essential controls inside the round 480x480 panel safe area. */
 headline=text(scene,progress_view?phase_title(shown.phase):"大肥鱼 · 陪着你",92,38,296,cream);lv_obj_set_style_text_align(headline,LV_TEXT_ALIGN_CENTER,0);
 if(progress_view){
  char round[64];if(shown.round)snprintf(round,sizeof(round),"第 %u 轮 · 真实任务进度",shown.round);else snprintf(round,sizeof(round),"真实任务进度");
  current_line=text(scene,round,108,72,264,muted);lv_obj_set_style_text_align(current_line,LV_TEXT_ALIGN_CENTER,0);
  const char *names[]={"接收任务","编排任务","执行确认","识别画面","下发指令","操作手机","核验结果","任务结束"};
  for(unsigned i=0;i<8;i++){
   lv_obj_t *row=lv_obj_create(scene);lv_obj_set_pos(row,84,100+i*30);lv_obj_set_size(row,312,29);lv_obj_remove_flag(row,LV_OBJ_FLAG_SCROLLABLE);
   lv_obj_set_style_border_width(row,0,0);lv_obj_set_style_radius(row,9,0);lv_obj_set_style_pad_all(row,0,0);
   bool active=shown.rows[i]==PC_CURRENT;lv_obj_set_style_bg_color(row,lv_color_hex(active?cream:0x24283f),0);
   badges[i]=text(row,shown.rows[i]==PC_FAILED?"!":shown.rows[i]==PC_COMPLETE?"✓":active?"●":"○",10,0,24,active?navy:shown.rows[i]==PC_FAILED?0xffb8a8:shown.rows[i]==PC_COMPLETE?green:muted);
   rows[i]=text(row,names[i],40,0,260,active?navy:shown.rows[i]==PC_COMPLETE?0xe0f1e6:muted);
  }
  detail=text(scene,shown.detail[0]?shown.detail:"等待真实事件，不补全未知步骤",84,344,312,muted);lv_label_set_long_mode(detail,LV_LABEL_LONG_WRAP);lv_obj_set_height(detail,54);
  bool local_plan=shown.phase==PC_CONFIRM&&amoled_plugin_stage()==1;
  if(local_plan)button("查看计划",84,398,148,42,64,cream,navy);
  if(shown.phase==PC_DONE||shown.phase==PC_ERROR||shown.phase==PC_STOPPED){
   lv_obj_t *ack=button("知道了",138,398,204,42,-1,cream,navy);lv_obj_add_event_cb(ack,toggle,LV_EVENT_CLICKED,NULL);
  }else{
   lv_obj_t *stop=button("停止任务",local_plan?248:138,398,local_plan?148:204,42,43,0x673734,0xffd6ce);
   if(shown.sealed)lv_obj_add_state(stop,LV_STATE_DISABLED);
  }
 }else{
  lv_obj_t *bubble=lv_obj_create(scene);lv_obj_set_pos(bubble,76,80);lv_obj_set_size(bubble,328,56);lv_obj_set_style_radius(bubble,24,0);lv_obj_set_style_bg_color(bubble,lv_color_hex(cream),0);lv_obj_set_style_border_width(bubble,0,0);lv_obj_remove_flag(bubble,LV_OBJ_FLAG_SCROLLABLE);
  detail=text(bubble,home_greeting(),0,0,308,navy);lv_obj_set_style_text_align(detail,LV_TEXT_ALIGN_CENTER,0);lv_obj_center(detail);
  lv_obj_t *floor=lv_obj_create(scene);lv_obj_remove_style_all(floor);lv_obj_set_style_bg_opa(floor,LV_OPA_COVER,0);lv_obj_set_pos(floor,120,340);lv_obj_set_size(floor,240,18);lv_obj_set_style_radius(floor,LV_RADIUS_CIRCLE,0);lv_obj_set_style_bg_color(floor,lv_color_hex(0x39344e),0);lv_obj_set_style_border_width(floor,0,0);lv_obj_remove_flag(floor,LV_OBJ_FLAG_SCROLLABLE);lv_obj_set_scrollbar_mode(floor,LV_SCROLLBAR_MODE_OFF);
  pet=lv_image_create(scene);lv_image_set_src(pet,&companion_pet[frame%8]);lv_obj_set_pos(pet,140,118);lv_obj_add_flag(pet,LV_OBJ_FLAG_CLICKABLE);lv_obj_add_event_cb(pet,pat,LV_EVENT_CLICKED,NULL);
  lv_obj_t *pat_button=button("摸摸它",84,368,148,48,-1,0x39354c,cream);lv_obj_add_event_cb(pat_button,pat,LV_EVENT_CLICKED,NULL);
  button("办件事",248,368,148,48,11,cream,navy);
  sync_line=text(scene,"",108,416,264,muted);lv_obj_set_style_text_align(sync_line,LV_TEXT_ALIGN_CENTER,0);
 }
 lv_obj_t *home=button("原首页",152,438,88,28,10,navy,muted);
 (void)home;
 if(has_task){lv_obj_t *switcher=button(progress_view?"陪伴":"进度",244,438,88,28,-1,navy,cream);lv_obj_add_event_cb(switcher,toggle,LV_EVENT_CLICKED,NULL);}
 was_patted=false;last_sync=~0u;needs_build=false;
}
void amoled_companion_ui_destroy(void){scene=pet=headline=detail=current_line=sync_line=NULL;}
void amoled_companion_ui_create(lv_obj_t *root,lv_event_cb_t action,bool blocked){
 handler=action;disabled=blocked;frame=0;last_frame=0;touch_until=0;
 amoled_companion_snapshot(&shown);has_task=shown.phase!=PC_IDLE;force_home=!has_task||shown.sealed;progress_view=has_task&&!force_home;
 scene=lv_obj_create(root);lv_obj_set_pos(scene,0,0);lv_obj_set_size(scene,480,480);lv_obj_set_style_pad_all(scene,0,0);lv_obj_set_style_border_width(scene,0,0);lv_obj_set_style_radius(scene,0,0);lv_obj_remove_flag(scene,LV_OBJ_FLAG_SCROLLABLE);build();
}
void amoled_companion_ui_tick(void){
 if(!scene)return;
 pc_companion next;amoled_companion_snapshot(&next);has_task=next.phase!=PC_IDLE;
 bool fresh=strcmp(next.task,shown.task)!=0||(!next.task[0]&&next.epoch!=shown.epoch);
 if(fresh&&has_task&&!next.sealed)force_home=false;
 bool mode=has_task&&!force_home;
 if(next.phase!=shown.phase||next.epoch!=shown.epoch||next.round!=shown.round||memcmp(next.rows,shown.rows,sizeof(next.rows))||mode!=progress_view||strcmp(next.detail,shown.detail)||needs_build){shown=next;progress_view=mode;build();}else shown=next;
 if(sync_line){unsigned sync=amoled_companion_monitor_state();if(sync!=last_sync){last_sync=sync;lv_label_set_text(sync_line,sync==3?"任务状态未同步":sync==1?"正在同步任务状态":"");}}
 if(pet){int64_t now=esp_timer_get_time();if(now-last_frame>=250000){last_frame=now;frame=(frame+1)%8;lv_image_set_src(pet,&companion_pet[frame]);}
  bool patted=now<touch_until;if(patted!=was_patted){lv_label_set_text(detail,patted?"嗯，我在这里陪你。":home_greeting());was_patted=patted;}}
}
