#include "dialogue.h"
#include "voice.h"
#include "adb_local.h"
#include "device_config.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "cJSON.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <cstring>
#include <cstdlib>
extern const char *controller_ota_endpoint();
static bool live(unsigned sequence){return controller_voice_cancel_sequence()<sequence;}
static int post(const char *path,unsigned sequence,const char *body,unsigned char *out,unsigned capacity){
 if(!live(sequence))return -1;
 char url[256],auth[128],seq[16];snprintf(url,sizeof(url),"%s%s",controller_ota_endpoint(),path);
 snprintf(auth,sizeof(auth),"Bearer %s",DISPLAY_TOKEN);snprintf(seq,sizeof(seq),"%u",sequence);
 esp_http_client_config_t cfg={};cfg.url=url;cfg.common_name="erweima.zhangyue.site";cfg.crt_bundle_attach=esp_crt_bundle_attach;cfg.timeout_ms=20000;cfg.disable_auto_redirect=true;
 auto c=esp_http_client_init(&cfg);if(!c)return -1;
 esp_http_client_set_method(c,HTTP_METHOD_POST);esp_http_client_set_header(c,"Authorization",auth);esp_http_client_set_header(c,"Host","erweima.zhangyue.site");
 esp_http_client_set_header(c,"Connection","close");esp_http_client_set_header(c,"X-Voice-Session",controller_voice_session());esp_http_client_set_header(c,"X-Voice-Sequence",seq);esp_http_client_set_header(c,"Content-Type","application/json");
 unsigned length=body?strlen(body):0;bool ok=esp_http_client_open(c,length)==ESP_OK;
 unsigned sent=0;while(ok&&sent<length&&live(sequence)){int n=esp_http_client_write(c,body+sent,length-sent);if(n<=0){ok=false;break;}sent+=n;}
 int used=0;
 if(ok&&sent==length&&live(sequence)&&esp_http_client_fetch_headers(c)>=0&&esp_http_client_get_status_code(c)==200){
  for(;;){if(!live(sequence)||used>=(int)capacity){ok=false;break;}int n=esp_http_client_read(c,(char*)out+used,capacity-used);if(n<0){ok=false;break;}if(n==0){ok=esp_http_client_is_complete_data_received(c);break;}used+=n;}
 }else ok=false;
 esp_http_client_close(c);esp_http_client_cleanup(c);return ok&&live(sequence)?used:-1;
}
static const char *str(cJSON *j,const char *key){auto v=cJSON_GetObjectItemCaseSensitive(j,key);return cJSON_IsString(v)?v->valuestring:"";}
bool controller_dialogue_run(unsigned sequence){
 auto output=(char*)heap_caps_malloc(48001,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
 if(!output)return false;
 bool success=false;int64_t until=esp_timer_get_time()+180000000;uint32_t ticket=controller_adb_ticket();
 controller_voice_state(10);
 while(live(sequence)&&esp_timer_get_time()<until){
  char response[2048];int n=post("/dialogue/poll",sequence,nullptr,(unsigned char*)response,sizeof(response)-1);
  if(n<0)break;
  response[n]=0;cJSON *j=cJSON_Parse(response);if(!j)break;
  const char *op=str(j,"op");
  if(!strcmp(op,"wait")){cJSON_Delete(j);vTaskDelay(pdMS_TO_TICKS(200));continue;}
  if(!strcmp(op,"done")){
   success=!strcmp(str(j,"state"),"done");bool audio=cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(j,"audio"));cJSON_Delete(j);
   auto frame=(unsigned char*)heap_caps_malloc(5001,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
   if(frame){if(post("/dialogue/screen",sequence,nullptr,frame,5001)==5000&&live(sequence))controller_dialogue_screen(frame);free(frame);}
   if(audio&&!controller_audio_muted()&&controller_audio_volume()>0){
    controller_voice_state(11);auto pcm=(unsigned char*)heap_caps_malloc(960001,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(pcm){int size=post("/dialogue/audio",sequence,nullptr,pcm,960001);if(size>0&&size<=960000&&!(size%2)&&live(sequence)){if(!controller_audio_play_pcm(pcm,size))success=false;}else success=false;free(pcm);}else success=false;
   }
   break;
  }
  controller::AdbCommand cmd{};bool valid=!strcmp(op,"type_text");
  if(valid){const char *v=str(j,"text_b64");valid=strlen(v)>0&&strlen(v)<sizeof(cmd.text_b64);if(valid)strcpy(cmd.text_b64,v);}
  const char *id=str(j,"id");if(strlen(id)!=32)valid=false;
  const char *error=valid?"cancelled":"invalid_command";
  ESP_LOGI("dialogue","Command received op=%s id=%.8s valid=%d",op,id,valid);
  bool ok=valid&&live(sequence)&&controller_adb_execute(cmd,nullptr,output,48001,ticket,&error);
  if(!ok)output[0]=0;
  cJSON *ack=cJSON_CreateObject();cJSON_AddStringToObject(ack,"id",id);cJSON_AddBoolToObject(ack,"ok",ok);cJSON_AddStringToObject(ack,"output",output);if(!ok)cJSON_AddStringToObject(ack,"error",error);
  char *body=cJSON_PrintUnformatted(ack);cJSON_Delete(ack);cJSON_Delete(j);
  char result[128];bool sent=body&&post("/dialogue/result",sequence,body,(unsigned char*)result,sizeof(result))>=0;free(body);
  ESP_LOGI("dialogue","Command result ok=%d error=%s ack=%d",ok,ok?"":error,sent);
  if(!sent)break;
 }
 free(output);return success&&live(sequence);
}
