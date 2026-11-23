#include "companion_speech.h"
#include "identity.h"
#include "wifi.h"
#include "bsp/esp-bsp.h"
#include "esp_codec_dev.h"
#include "driver/gpio.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include <stdatomic.h>
#include "nvs.h"
#ifdef ESP_PLATFORM
#include "esp_log.h"
#endif
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "cJSON.h"
#include <string.h>
#include <stdio.h>
static companion_speech_state state;
static portMUX_TYPE lock=portMUX_INITIALIZER_UNLOCKED;
static esp_codec_dev_handle_t speaker;
static atomic_uint output_volume=70;
void companion_speech_init(void){
#ifdef ESP_PLATFORM
 nvs_handle_t h;uint8_t v;
 if(nvs_open("pet_voice",NVS_READONLY,&h)==ESP_OK){if(nvs_get_u8(h,"volume",&v)==ESP_OK&&v<=100)atomic_store(&output_volume,v);nvs_close(h);}
#endif
}
unsigned companion_speech_volume(void){return atomic_load(&output_volume);}
void companion_speech_set_volume(unsigned volume){
 if(volume>100)volume=100;
 atomic_store(&output_volume,volume);
#ifdef ESP_PLATFORM
 nvs_handle_t h;if(nvs_open("pet_voice",NVS_READWRITE,&h)==ESP_OK){nvs_set_u8(h,"volume",volume);nvs_commit(h);nvs_close(h);}
#endif
}
static bool play_begin(unsigned epoch,bool (*live)(uint32_t));
static bool play_write(const uint8_t *pcm,size_t size,unsigned epoch,bool (*live)(uint32_t));
static void play_end(void);

static void update(unsigned stage,const char *detail,const char *heard,const char *reply){
 taskENTER_CRITICAL(&lock);state.stage=stage;
 if(detail)snprintf(state.detail,sizeof(state.detail),"%s",detail);
 if(heard)snprintf(state.heard,sizeof(state.heard),"%s",heard);
 if(reply)snprintf(state.reply,sizeof(state.reply),"%s",reply);
 taskEXIT_CRITICAL(&lock);
}
void companion_speech_reset(void){taskENTER_CRITICAL(&lock);memset(&state,0,sizeof(state));taskEXIT_CRITICAL(&lock);}
void companion_speech_snapshot(companion_speech_state *out){taskENTER_CRITICAL(&lock);*out=state;taskEXIT_CRITICAL(&lock);}
static void download_progress(size_t received,size_t total){
 taskENTER_CRITICAL(&lock);state.received=received;state.total=total;state.stage=5;
 unsigned percent=total?(unsigned)((uint64_t)received*100/total):0;
 snprintf(state.detail,sizeof(state.detail),"正在下载播报音频 %u%%",percent);taskEXIT_CRITICAL(&lock);
}
static const char *str(cJSON *o,const char *key){cJSON *v=cJSON_GetObjectItemCaseSensitive(o,key);return cJSON_IsString(v)?v->valuestring:"";}
static bool request(const char *path,bool post,const uint8_t *input,size_t size,unsigned epoch,const char *session,bool (*live)(uint32_t),uint8_t **out,size_t *used,size_t limit,size_t expected_audio,bool stopping){
 *out=NULL;*used=0;if(!amoled_wifi_connected()||(!stopping&&!live(epoch)))return false;
 char endpoint[191],url[256];if(!amoled_wifi_endpoint(endpoint,sizeof(endpoint)))return false;
 snprintf(url,sizeof(url),"%s%s",endpoint,path);
 bool bulk=size>0||limit>2048;
 int64_t deadline=esp_timer_get_time()+(stopping?5000000:limit>2048?60000000:30000000);
 esp_http_client_config_t cfg={.url=url,.timeout_ms=3000,.crt_bundle_attach=esp_crt_bundle_attach,.disable_auto_redirect=true,.buffer_size=1024,.keep_alive_enable=false};
 esp_http_client_handle_t c=esp_http_client_init(&cfg);if(!c)return false;
 wifi_ps_type_t previous_ps=WIFI_PS_MIN_MODEM;bool restore_ps=false;
 if(bulk&&esp_wifi_get_ps(&previous_ps)==ESP_OK&&previous_ps!=WIFI_PS_NONE)restore_ps=esp_wifi_set_ps(WIFI_PS_NONE)==ESP_OK;
 bool ok=amoled_identity_http_auth(c)==ESP_OK;
 esp_http_client_set_method(c,post?HTTP_METHOD_POST:HTTP_METHOD_GET);
 esp_http_client_set_header(c,"X-Voice-Session",session);esp_http_client_set_header(c,"X-Voice-Sequence","1");
 esp_http_client_set_header(c,"Content-Type","application/octet-stream");esp_http_client_set_header(c,"Connection","close");
 ok=ok&&esp_http_client_open(c,post?size:0)==ESP_OK;size_t sent=0;
 while(ok&&sent<size){
  if((!stopping&&!live(epoch))||esp_timer_get_time()>=deadline){ok=false;break;}
  size_t n=size-sent;if(n>4096)n=4096;int wrote=esp_http_client_write(c,(const char *)input+sent,n);if(wrote<=0){ok=false;break;}sent+=wrote;
 }
 uint8_t *body=NULL;int64_t length=-1;int status=0;bool playing=false;
 if(ok){
  length=esp_http_client_fetch_headers(c);status=esp_http_client_get_status_code(c);
  ok=length>=0&&length<=(int64_t)limit&&(status==200||status==202)&&!esp_http_client_is_chunked_response(c);
  if(expected_audio)ok=ok&&length==(int64_t)expected_audio&&length%2==0;
  if(ok){body=heap_caps_malloc(length+1,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);ok=body!=NULL;}
  if(ok&&expected_audio){playing=play_begin(epoch,live);ok=playing;}
  if(ok&&limit>2048)download_progress(0,length);
  size_t streamed=0;
  while(ok&&*used<(size_t)length){
   if((!stopping&&!live(epoch))||esp_timer_get_time()>=deadline){ok=false;break;}
   size_t wanted=(size_t)length-*used;if(wanted>4096)wanted=4096;
   int n=esp_http_client_read(c,(char *)body+*used,wanted);if(n<=0){ok=false;break;}*used+=n;
   if(limit>2048)download_progress(*used,length);
   if(expected_audio){size_t complete=*used&~(size_t)1;if(complete>streamed){ok=play_write(body+streamed,complete-streamed,epoch,live);streamed=complete;}}
  }
  ok=ok&&esp_http_client_is_complete_data_received(c);
 }
 if(playing){if(ok&&live(epoch))vTaskDelay(pdMS_TO_TICKS(100));play_end();}
 esp_http_client_close(c);esp_http_client_cleanup(c);
 if(restore_ps)esp_wifi_set_ps(previous_ps);
 ok=ok&&esp_timer_get_time()<deadline&&(stopping||live(epoch));
 if(!ok){
#ifdef ESP_PLATFORM
  if(!stopping)ESP_LOGW("pet_voice","request failed path=%s status=%d bytes=%u/%lld deadline=%d",path,status,(unsigned)*used,(long long)length,esp_timer_get_time()>=deadline);
#endif
  if(body)heap_caps_free(body);
  return false;
 }
 body[*used]=0;*out=body;return true;
}
static cJSON *json_request(const char *path,bool post,const uint8_t *pcm,size_t size,unsigned epoch,const char *session,bool (*live)(uint32_t),bool stopping){
 uint8_t *body;size_t count;if(!request(path,post,pcm,size,epoch,session,live,&body,&count,2048,0,stopping))return NULL;
 for(size_t i=0;i+5<count;i++)if(!memcmp(body+i,"\\u0000",6)){heap_caps_free(body);return NULL;}
 cJSON *o=cJSON_ParseWithOpts((const char *)body,NULL,true);heap_caps_free(body);
 cJSON *seq=cJSON_GetObjectItemCaseSensitive(o,"sequence");
 if(!cJSON_IsObject(o)||strcmp(str(o,"session"),session)||!cJSON_IsNumber(seq)||seq->valuedouble!=1){cJSON_Delete(o);return NULL;}
 return o;
}
static void amp_off(void){gpio_set_level(BSP_POWER_AMP_IO,0);}
void companion_speech_stop(void){amp_off();update(9,"本地已停止，正在取消本轮对话",NULL,NULL);}
static void play_end(void){
 amp_off();if(speaker){esp_codec_dev_set_out_mute(speaker,true);esp_codec_dev_set_out_vol(speaker,0);esp_codec_dev_close(speaker);}
}
static bool play_begin(unsigned epoch,bool (*live)(uint32_t)){
 amp_off();if(!speaker)speaker=bsp_audio_codec_speaker_init();if(!speaker)return false;
 esp_codec_dev_sample_info_t format={.sample_rate=16000,.channel=1,.bits_per_sample=16};
 if(esp_codec_dev_open(speaker,&format)!=ESP_CODEC_DEV_OK)return false;
 amp_off();esp_codec_dev_set_out_mute(speaker,true);esp_codec_dev_set_out_vol(speaker,0);
 int16_t silence[256]={0};
 if(esp_codec_dev_write(speaker,silence,sizeof(silence))!=ESP_CODEC_DEV_OK||!live(epoch)){play_end();return false;}
 return true;
}
static bool play_write(const uint8_t *pcm,size_t size,unsigned epoch,bool (*live)(uint32_t)){
 unsigned volume=companion_speech_volume();
 if(!live(epoch)||esp_codec_dev_set_out_vol(speaker,volume)!=ESP_CODEC_DEV_OK||esp_codec_dev_set_out_mute(speaker,volume==0)!=ESP_CODEC_DEV_OK)return false;
 if(gpio_set_level(BSP_POWER_AMP_IO,volume?1:0)!=ESP_OK)return false;
 update(6,"正在接收并播报回答",NULL,NULL);
 for(size_t offset=0;offset<size;){
  if(!live(epoch))return false;
  size_t n=size-offset;if(n>1024)n=1024;
  if(esp_codec_dev_write(speaker,(void *)(pcm+offset),n)!=ESP_CODEC_DEV_OK)return false;
  offset+=n;
 }
 return live(epoch);
}
bool companion_speech_run(const uint8_t *pcm,size_t size,unsigned epoch,const char *session,bool (*live)(uint32_t)){
 bool speaker_failed=false;
 update(1,"正在上传录音到106",NULL,NULL);
 cJSON *o=json_request("/board-voice",true,pcm,size,epoch,session,live,false);
 if(!o)goto fail;
 cJSON_Delete(o);
 int64_t until=esp_timer_get_time()+210000000;
 while(live(epoch)&&esp_timer_get_time()<until){
  o=json_request("/board-voice/status",false,NULL,0,epoch,session,live,false);if(!o)goto fail;
  const char *phase=str(o,"state");unsigned stage=!strcmp(phase,"recognizing")?2:!strcmp(phase,"queued")?3:!strcmp(phase,"thinking")?4:!strcmp(phase,"synthesizing")?5:0;
  if(strlen(str(o,"recognizedText"))>480||strlen(str(o,"reply"))>480){cJSON_Delete(o);goto fail;}
  update(stage,str(o,"detail"),str(o,"recognizedText"),str(o,"reply"));
  if(!strcmp(phase,"ready")){
   cJSON *length=cJSON_GetObjectItemCaseSensitive(o,"audioBytes");size_t expected=cJSON_IsNumber(length)&&length->valuedouble>0&&length->valuedouble<=960000?(size_t)length->valuedouble:0;cJSON_Delete(o);
   update(5,"正在下载播报音频",NULL,NULL);
   uint8_t *audio=NULL;size_t count=0;
   if(!expected||expected%2||!request("/board-voice/audio",false,NULL,0,epoch,session,live,&audio,&count,960000,expected,false))goto fail;
   bool framing_ok=count==expected;bool ok=framing_ok&&live(epoch);memset(audio,0,count);heap_caps_free(audio);
   if(!ok){speaker_failed=framing_ok&&live(epoch);goto fail;}
   o=json_request("/board-voice/played",true,NULL,0,epoch,session,live,false);cJSON_Delete(o);
   update(7,"回答播报已结束",NULL,NULL);return true;
  }
  bool failed=!strcmp(phase,"error")||!strcmp(phase,"stopped");cJSON_Delete(o);if(failed)goto fail;
  vTaskDelay(pdMS_TO_TICKS(600));
 }
 fail:
 amp_off();bool stopped=!live(epoch);
 o=json_request("/board-voice/stop",true,NULL,0,epoch,session,live,true);cJSON_Delete(o);
 update(stopped?9:8,stopped?"本轮语音已停止":speaker_failed?"播报未完成，文字回答已保留":"语音连接未完成，请稍后重试",NULL,NULL);return false;
}

bool companion_speech_test(unsigned epoch,bool (*live)(uint32_t)){
 if(!play_begin(epoch,live))return false;
 int16_t pcm[256];for(unsigned i=0;i<256;i++)pcm[i]=i%32<16?2000:-2000;
 bool ok=true;for(unsigned i=0;i<32&&ok;i++)ok=play_write((const uint8_t*)pcm,sizeof(pcm),epoch,live);
 if(ok)vTaskDelay(pdMS_TO_TICKS(100));
 play_end();update(ok?7:8,ok?"试音已结束":"试音未完成",NULL,NULL);return ok;
}
