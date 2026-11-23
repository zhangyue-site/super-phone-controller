#include "companion_ui.h"
#include "companion_task.h"
#include "companion_monitor.h"
#include "plugin.h"
#include "audio.h"
#include "companion_speech.h"
#include "pet/pet_assets.h"
#include "esp_timer.h"
#ifdef ESP_PLATFORM
#include "esp_log.h"
#endif
LV_FONT_DECLARE(companion_font);
static lv_obj_t *scene,*pet,*headline,*detail,*rows[8],*badges[8],*current_line,*sync_line;
static lv_event_cb_t handler;
static bool disabled,power_blocked,starting,progress_view,has_task,force_home,needs_build;
static int64_t touch_until,last_frame;
static unsigned frame;
static bool was_patted;
static unsigned tap_cycle,tap_revision,shown_tap_revision,tap_action;
static int64_t tap_started;
static const char *tap_message="嗯，我在这里陪你。";
static bool voice_view,voice_held,voice_busy,voice_settings;
static char settings_notice[160];
static lv_obj_t *voice_stage,*voice_heard,*voice_answer,*volume_label;
static void volume_change(lv_event_t *e){
 int v=(int)companion_speech_volume()+(int)(intptr_t)lv_event_get_user_data(e);if(v<0)v=0;if(v>100)v=100;companion_speech_set_volume(v);
 if(volume_label){char b[32];snprintf(b,sizeof(b),"音量 %d%%",v);lv_label_set_text(volume_label,b);}
}
static unsigned last_sync;
static pc_companion shown;
static const uint32_t navy=0x141729,cream=0xffe4ba,muted=0xb9bed2,green=0x8cdda7;
static lv_obj_t *text(lv_obj_t *p,const char *value,int x,int y,int w,uint32_t color){
 lv_obj_t *o=lv_label_create(p);lv_label_set_text(o,value);lv_obj_set_pos(o,x,y);lv_obj_set_width(o,w);
 lv_obj_set_style_text_font(o,&companion_font,0);lv_obj_set_style_text_color(o,lv_color_hex(color),0);lv_label_set_long_mode(o,LV_LABEL_LONG_DOT);return o;
}
static void toggle(lv_event_t *e){(void)e;force_home=!force_home;needs_build=true;}
static void voice_hold(lv_event_t *e){
 if(disabled)return;
 lv_event_code_t code=lv_event_get_code(e);
 if(code==LV_EVENT_PRESSED){
  if(amoled_audio_chat_press()){voice_held=true;touch_until=0;}
  else{if(detail)lv_label_set_text(detail,amoled_audio_unavailable_reason());return;}
 }else if(code==LV_EVENT_RELEASED&&voice_held){voice_held=false;amoled_audio_release();voice_view=true;needs_build=true;}
 else if(code==LV_EVENT_PRESS_LOST&&voice_held){voice_held=false;amoled_audio_cancel();voice_view=true;needs_build=true;}
}
static void voice_settings_open(lv_event_t *e){(void)e;voice_settings=true;settings_notice[0]=0;needs_build=true;}
static void voice_settings_back(lv_event_t *e){(void)e;voice_settings=false;needs_build=true;}
static void voice_test(lv_event_t *e){(void)e;settings_notice[0]=0;
 if(!amoled_audio_test_speaker())snprintf(settings_notice,sizeof(settings_notice),"%s",amoled_audio_unavailable_reason());
 needs_build=true;
}
static void voice_stop(lv_event_t *e){(void)e;amoled_audio_cancel();needs_build=true;}
static void voice_back(lv_event_t *e){(void)e;if(amoled_audio_busy())amoled_audio_cancel();voice_view=false;needs_build=true;}
/* Keep every transformed corner between the speech bubble and action buttons.
 * A new tap replaces the current reaction; no animation queue survives a page. */
static void pet_pose(int64_t now){
 if(!pet||!tap_action)return;
 int elapsed=(int)((now-tap_started)/1000);if(elapsed<0)elapsed=0;
 int x=140,y=114,angle=0,sx=240,sy=240;
 if(tap_action==1&&elapsed<640)y-=56*elapsed*(640-elapsed)/(640*640);
 else if(tap_action==2&&elapsed<720){
  angle=elapsed<180?elapsed*25/180:elapsed<360?(360-elapsed)*25/180:elapsed<540?-(elapsed-360)*25/180:-(720-elapsed)*25/180;
  x+=angle/4;
 }else if(tap_action==3&&elapsed<600){
  int pulse=elapsed<300?elapsed:600-elapsed;sx+=16*pulse/300;sy-=16*pulse/300;
 }
 lv_obj_set_pos(pet,x,y);lv_image_set_rotation(pet,angle);lv_image_set_scale_x(pet,sx);lv_image_set_scale_y(pet,sy);
 if(elapsed>=720)tap_action=0;
}
static void pat(lv_event_t *e){
 (void)e;if(!pet||disabled)return;
 static const char *messages[]={"好呀，跳一下给你看！","听见啦，我在陪着你。","嘿嘿，被你摸到了。"};
 tap_action=tap_cycle%3+1;tap_message=messages[tap_cycle%3];tap_cycle++;tap_revision++;
 tap_started=esp_timer_get_time();touch_until=tap_started+2200000;pet_pose(tap_started);
#ifdef ESP_PLATFORM
 ESP_LOGI("pet","local tap=%u reaction=%u",tap_revision,tap_action);
#endif
}
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
 if(starting)return "正在启动，马上陪你。";
 if(shown.phase==PC_DONE)return "办好了，看看结果吧。";
 if(shown.phase==PC_ERROR)return "这次没完成，原因在进度里。";
 if(shown.phase==PC_STOPPED)return "已经停下来了，我在呢。";
 return "我在呢，今天想做点什么？";
}
static void set_text(lv_obj_t *o,const char *text){if(o&&strcmp(lv_label_get_text(o),text))lv_label_set_text(o,text);}
static void voice_update(void){
 companion_speech_state v;companion_speech_snapshot(&v);unsigned stage=amoled_audio_stage();char title[192];
 if(voice_settings){set_text(voice_stage,settings_notice[0]?settings_notice:amoled_audio_busy()?(v.detail[0]?v.detail:"正在试音"):amoled_audio_test_result()==2?"试音流程已结束，请确认声音":amoled_audio_test_result()==3?"试音未完成，请再次尝试":"调好音量后，点下方试音");return;}
 if(stage==1)snprintf(title,sizeof(title),"录音中 · %u秒 · 松手发送",amoled_audio_duration_ms()/1000);
 else if(amoled_audio_busy()&&stage==0)snprintf(title,sizeof(title),"正在准备麦克风");
 else snprintf(title,sizeof(title),"%s",stage==5?"本地已停止，迟到回答不再播报":stage==4&&!v.detail[0]?"录音未完成，请再试一次":v.detail[0]?v.detail:stage==5?"本轮语音已停止":"按住说话，松手查看回答");
 set_text(voice_stage,title);set_text(voice_heard,v.heard[0]?v.heard:"识别文字会显示在这里");set_text(voice_answer,v.reply[0]?v.reply:"龙虾的回答会显示在这里，并用喇叭播报。");
}
static void build(void){
 touch_until=0;tap_action=0;
 lv_obj_clean(scene);pet=headline=detail=current_line=sync_line=NULL;memset(rows,0,sizeof(rows));memset(badges,0,sizeof(badges));
 lv_obj_set_style_bg_color(scene,lv_color_hex(navy),0);
 voice_stage=voice_heard=voice_answer=volume_label=NULL;
 if(voice_view&&voice_settings){
  text(scene,"声音设置",164,40,180,cream);
  char vb[40];snprintf(vb,sizeof(vb),"音量 %u%%",companion_speech_volume());volume_label=text(scene,vb,124,100,232,cream);lv_obj_set_style_text_align(volume_label,LV_TEXT_ALIGN_CENTER,0);
  voice_stage=text(scene,"",84,150,312,muted);lv_obj_set_height(voice_stage,60);lv_label_set_long_mode(voice_stage,LV_LABEL_LONG_WRAP);
  lv_obj_t *minus=button("减小音量",84,222,148,58,-1,0x39354c,cream);lv_obj_add_event_cb(minus,volume_change,LV_EVENT_CLICKED,(void*)(intptr_t)-10);
  lv_obj_t *plus=button("增大音量",248,222,148,58,-1,0x39354c,cream);lv_obj_add_event_cb(plus,volume_change,LV_EVENT_CLICKED,(void*)(intptr_t)10);
  voice_busy=amoled_audio_busy();lv_obj_t *test=button(voice_busy?"停止语音":"播放试音",84,300,312,60,-1,voice_busy?0x673734:cream,voice_busy?0xffd6ce:navy);lv_obj_add_event_cb(test,voice_busy?voice_stop:voice_test,LV_EVENT_CLICKED,NULL);
  lv_obj_t *back=button("返回对话",138,388,204,52,-1,0x39354c,cream);lv_obj_add_event_cb(back,voice_settings_back,LV_EVENT_CLICKED,NULL);
  voice_update();needs_build=false;return;
 }
 if(voice_view){
  lv_obj_t *title=text(scene,"大肥鱼 · 语音对话",92,36,296,cream);lv_obj_set_style_text_align(title,LV_TEXT_ALIGN_CENTER,0);
  voice_stage=text(scene,"",84,76,312,muted);lv_label_set_long_mode(voice_stage,LV_LABEL_LONG_WRAP);lv_obj_set_height(voice_stage,44);
  lv_obj_t *heard=lv_obj_create(scene);lv_obj_set_pos(heard,84,126);lv_obj_set_size(heard,312,70);lv_obj_set_style_pad_all(heard,8,0);lv_obj_set_style_border_width(heard,0,0);lv_obj_set_style_bg_color(heard,lv_color_hex(0x24283f),0);
  voice_heard=text(heard,"",0,0,282,cream);lv_label_set_long_mode(voice_heard,LV_LABEL_LONG_WRAP);lv_obj_set_style_text_line_space(voice_heard,4,0);
  lv_obj_t *answer=lv_obj_create(scene);lv_obj_set_pos(answer,76,204);lv_obj_set_size(answer,328,112);lv_obj_set_style_pad_all(answer,10,0);lv_obj_set_style_border_width(answer,0,0);lv_obj_set_style_bg_color(answer,lv_color_hex(0x24283f),0);
  voice_answer=text(answer,"",0,0,294,0xe1e5ef);lv_label_set_long_mode(voice_answer,LV_LABEL_LONG_WRAP);lv_obj_set_style_text_line_space(voice_answer,4,0);
  voice_busy=amoled_audio_busy();
  if(voice_busy){lv_obj_t *stop=button("停止语音",84,326,312,60,-1,0x673734,0xffd6ce);lv_obj_add_event_cb(stop,voice_stop,LV_EVENT_CLICKED,NULL);}
  else{lv_obj_t *speak=button("按住说话",84,326,312,60,-1,cream,navy);lv_obj_add_event_cb(speak,voice_hold,LV_EVENT_ALL,NULL);}
  lv_obj_t *settings=button("音量设置",84,398,148,52,-1,0x39354c,cream);lv_obj_add_event_cb(settings,voice_settings_open,LV_EVENT_CLICKED,NULL);
  lv_obj_t *back=button("返回陪伴",248,398,148,52,-1,0x39354c,cream);lv_obj_add_event_cb(back,voice_back,LV_EVENT_CLICKED,NULL);
  voice_update();needs_build=false;return;
 }
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
  detail=text(scene,shown.detail[0]?shown.detail:"等待真实事件，不补全未知步骤",84,344,312,muted);lv_label_set_long_mode(detail,LV_LABEL_LONG_WRAP);lv_obj_set_height(detail,48);
  bool local_plan=shown.phase==PC_CONFIRM&&amoled_plugin_stage()==1;
  if(local_plan)button("查看计划",84,398,148,42,64,cream,navy);
  if(shown.phase==PC_DONE||shown.phase==PC_ERROR||shown.phase==PC_STOPPED){
   lv_obj_t *ack=button("知道了",138,398,204,42,-1,cream,navy);lv_obj_add_event_cb(ack,toggle,LV_EVENT_CLICKED,NULL);
  }else{
   lv_obj_t *stop=button("停止任务",local_plan?248:138,398,local_plan?148:204,42,43,0x673734,0xffd6ce);
   if(shown.sealed)lv_obj_add_state(stop,LV_STATE_DISABLED);
  }
 }else{
  lv_obj_t *bubble=lv_obj_create(scene);lv_obj_set_pos(bubble,76,68);lv_obj_set_size(bubble,328,44);lv_obj_set_style_radius(bubble,24,0);lv_obj_set_style_bg_color(bubble,lv_color_hex(cream),0);lv_obj_set_style_border_width(bubble,0,0);lv_obj_remove_flag(bubble,LV_OBJ_FLAG_SCROLLABLE);
  detail=text(bubble,home_greeting(),0,0,308,navy);lv_obj_set_style_text_align(detail,LV_TEXT_ALIGN_CENTER,0);lv_obj_center(detail);
  lv_obj_t *floor=lv_obj_create(scene);lv_obj_remove_style_all(floor);lv_obj_set_style_bg_opa(floor,LV_OPA_COVER,0);lv_obj_set_pos(floor,120,340);lv_obj_set_size(floor,240,18);lv_obj_set_style_radius(floor,LV_RADIUS_CIRCLE,0);lv_obj_set_style_bg_color(floor,lv_color_hex(0x39344e),0);lv_obj_set_style_border_width(floor,0,0);lv_obj_remove_flag(floor,LV_OBJ_FLAG_SCROLLABLE);lv_obj_set_scrollbar_mode(floor,LV_SCROLLBAR_MODE_OFF);
  pet=lv_image_create(scene);lv_image_set_src(pet,&companion_pet[frame%8]);lv_obj_set_pos(pet,140,114);lv_image_set_pivot(pet,100,232);lv_image_set_scale(pet,240);lv_obj_add_flag(pet,LV_OBJ_FLAG_CLICKABLE);lv_obj_add_event_cb(pet,pat,LV_EVENT_CLICKED,NULL);
  lv_obj_t *pat_button=button("按住说话",84,358,148,56,-1,0x39354c,cream);lv_obj_add_event_cb(pat_button,voice_hold,LV_EVENT_ALL,NULL);
  button("办件事",248,358,148,56,11,cream,navy);
  sync_line=text(scene,"",108,416,264,muted);lv_obj_set_height(sync_line,24);lv_obj_set_style_text_align(sync_line,LV_TEXT_ALIGN_CENTER,0);
 }
 lv_obj_t *home=button("原首页",152,442,88,28,61,navy,muted);
 (void)home;
 if(has_task){lv_obj_t *switcher=button(progress_view?"陪伴":"进度",244,442,88,28,-1,navy,cream);lv_obj_add_event_cb(switcher,toggle,LV_EVENT_CLICKED,NULL);}
 was_patted=false;shown_tap_revision=~0u;last_sync=~0u;needs_build=false;
}
void amoled_companion_ui_destroy(void){scene=pet=headline=detail=current_line=sync_line=voice_stage=voice_heard=voice_answer=volume_label=NULL;}
void amoled_companion_ui_set_starting(bool value){starting=value;disabled=power_blocked||starting;if(scene)needs_build=true;}
void amoled_companion_ui_create(lv_obj_t *root,lv_event_cb_t action,bool blocked){
 handler=action;power_blocked=blocked;disabled=blocked||starting;frame=0;voice_view=false;voice_settings=false;voice_held=false;last_frame=0;touch_until=0;
 amoled_companion_snapshot(&shown);has_task=shown.phase!=PC_IDLE;force_home=!has_task||shown.sealed;progress_view=has_task&&!force_home;
 scene=lv_obj_create(root);lv_obj_set_pos(scene,0,0);lv_obj_set_size(scene,480,480);lv_obj_set_style_pad_all(scene,0,0);lv_obj_set_style_border_width(scene,0,0);lv_obj_set_style_radius(scene,0,0);lv_obj_remove_flag(scene,LV_OBJ_FLAG_SCROLLABLE);build();
}
void amoled_companion_ui_tick(void){
 if(!scene)return;
 if(voice_held){char recording[96];snprintf(recording,sizeof(recording),amoled_audio_stage()==1?"录音中 · %u秒 · 松手发送":amoled_audio_stage()==0?"正在准备麦克风":"录音已结束，请松手查看回答",amoled_audio_duration_ms()/1000);set_text(detail,recording);if(voice_stage)set_text(voice_stage,recording);return;}
 if(voice_view){if(needs_build||voice_busy!=amoled_audio_busy())build();voice_update();return;}
 pc_companion next;amoled_companion_snapshot(&next);has_task=next.phase!=PC_IDLE;
 bool fresh=strcmp(next.task,shown.task)!=0||(!next.task[0]&&next.epoch!=shown.epoch);
 if(fresh&&has_task&&!next.sealed)force_home=false;
 bool mode=has_task&&!force_home;
 if(next.phase!=shown.phase||next.epoch!=shown.epoch||next.round!=shown.round||memcmp(next.rows,shown.rows,sizeof(next.rows))||mode!=progress_view||strcmp(next.detail,shown.detail)||needs_build){shown=next;progress_view=mode;build();}else shown=next;
 if(sync_line){unsigned sync=amoled_companion_monitor_state();if(sync!=last_sync){last_sync=sync;lv_label_set_text(sync_line,starting?"首次升级正在自检，请稍候":sync==3?"任务状态未同步":sync==1?"正在同步任务状态":"");}}
 if(pet){int64_t now=esp_timer_get_time();if(!starting&&now-last_frame>=250000){last_frame=now;frame=(frame+1)%8;lv_image_set_src(pet,&companion_pet[frame]);}
  pet_pose(now);
  bool patted=now<touch_until;if(patted!=was_patted||shown_tap_revision!=tap_revision){lv_label_set_text(detail,patted?tap_message:home_greeting());was_patted=patted;shown_tap_revision=tap_revision;}}
}
