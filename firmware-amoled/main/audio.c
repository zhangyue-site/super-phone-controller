#include "audio.h"
#include "audio_policy.h"
#include "identity.h"
#include "wifi.h"
#include "relay.h"
#include "usb.h"
#include "ota_ble.h"
#include "bsp/esp-bsp.h"
#include "esp_codec_dev.h"
#include "driver/gpio.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "cJSON.h"
#include <stdatomic.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <math.h>
#include <time.h>
static atomic_bool held,busy;
static atomic_uint generation=1,stage,duration;
static esp_codec_dev_handle_t microphone;
static bool codec_attempted;
static portMUX_TYPE result_lock=portMUX_INITIALIZER_UNLOCKED;
static char recognized_text[481];
static void clear_result(void){taskENTER_CRITICAL(&result_lock);memset(recognized_text,0,sizeof(recognized_text));taskEXIT_CRITICAL(&result_lock);}
bool amoled_audio_result(char *out,size_t size){
 if(!out||size<sizeof(recognized_text))return false;
 taskENTER_CRITICAL(&result_lock);memcpy(out,recognized_text,sizeof(recognized_text));taskEXIT_CRITICAL(&result_lock);return out[0]!=0;
}
bool amoled_audio_busy(void){return atomic_load(&busy);}
unsigned amoled_audio_stage(void){return atomic_load(&stage);}
unsigned amoled_audio_duration_ms(void){return atomic_load(&duration);}
void amoled_audio_release(void){atomic_store(&held,false);}
void amoled_audio_cancel(void){
 atomic_fetch_add(&generation,1);atomic_store(&held,false);
 clear_result();
 atomic_store(&stage,amoled_audio_busy()?5:0);
}
static bool live(unsigned epoch){
 return atomic_load(&generation)==epoch&&amoled_relay_audio_owned()&&amoled_wifi_connected()&&
  !amoled_relay_connected()&&!amoled_ota_busy();
}
static bool amplifier_off(void){
 /* Capture never initializes ES8311 OUT, opens its DAC, unmutes it, or powers PA. */
 gpio_config_t pin={.pin_bit_mask=1ULL<<BSP_POWER_AMP_IO,.mode=GPIO_MODE_OUTPUT};
 return gpio_config(&pin)==ESP_OK&&gpio_set_level(BSP_POWER_AMP_IO,0)==ESP_OK;
}
static bool microphone_open(void){
 if(!amplifier_off())return false;
 if(!codec_attempted){codec_attempted=true;microphone=bsp_audio_codec_microphone_init();}
 if(!microphone)return false;
 esp_codec_dev_sample_info_t format={.sample_rate=16000,.channel=1,.bits_per_sample=16};
 if(esp_codec_dev_open(microphone,&format)!=ESP_CODEC_DEV_OK)return false;
 if(esp_codec_dev_set_in_gain(microphone,30.0f)!=ESP_CODEC_DEV_OK){
  esp_codec_dev_close(microphone);return false;
 }
 return true;
}
static void close_http(esp_http_client_handle_t client){
 if(client){esp_http_client_close(client);esp_http_client_cleanup(client);}
}
static bool upload(const uint8_t *pcm,size_t size,unsigned epoch,const char *session,bool stop){
 if(!stop&&(!live(epoch)||size<12800||size>320000||size%2))return false;
 if(!amoled_wifi_connected()||time(NULL)<1700000000)return false;
 char endpoint[191],url[320],response[1025];size_t used=0,sent=0;
 int64_t deadline=esp_timer_get_time()+(stop?5000000:90000000);
 if(!amoled_wifi_endpoint(endpoint,sizeof(endpoint)))return false;
 int n=snprintf(url,sizeof(url),"%s%s",endpoint,stop?"/stop":"/voice");
 if(n<0||n>=(int)sizeof(url))return false;
 esp_http_client_config_t cfg={.url=url,.timeout_ms=stop?2000:5000,.crt_bundle_attach=esp_crt_bundle_attach,
  .disable_auto_redirect=true,.buffer_size=2048,.keep_alive_enable=false};
 esp_http_client_handle_t client=esp_http_client_init(&cfg);if(!client)return false;
 bool ok=amoled_identity_http_auth(client)==ESP_OK;
 esp_http_client_set_method(client,HTTP_METHOD_POST);
 esp_http_client_set_header(client,"X-Voice-Session",session);
 esp_http_client_set_header(client,"X-Voice-Sequence","1");
 if(!stop)esp_http_client_set_header(client,"X-Voice-Result","text-v1");
 esp_http_client_set_header(client,"Content-Type","application/octet-stream");
 esp_http_client_set_header(client,"Connection","close");
 /* No X-Voice-Dialogue: this slice recognizes only and never starts HID tasks. */
 ok=ok&&esp_http_client_open(client,stop?0:size)==ESP_OK;
 while(ok&&!stop&&sent<size){
  if(!live(epoch)||esp_timer_get_time()>=deadline){ok=false;break;}
  size_t count=size-sent;if(count>4096)count=4096;
  int written=esp_http_client_write(client,(const char *)pcm+sent,count);
  if(written<=0){ok=false;break;}sent+=written;
 }
 if(ok&&(stop||live(epoch))&&esp_timer_get_time()<deadline){
  int64_t length=esp_http_client_fetch_headers(client);
  ok=length>=0&&length<=1024&&esp_http_client_get_status_code(client)==200&&!esp_http_client_is_chunked_response(client);
  while(ok&&used<(size_t)length){
   if((!stop&&!live(epoch))||esp_timer_get_time()>=deadline){ok=false;break;}
   int got=esp_http_client_read(client,response+used,length-used);
   if(got<=0){ok=false;break;}used+=got;
  }
  ok=ok&&esp_http_client_is_complete_data_received(client);
 }else ok=false;
 close_http(client);
 if(!ok||(!stop&&!live(epoch))||esp_timer_get_time()>=deadline)return false;
 if(stop)return true;
 response[used]=0;
 for(size_t i=0;i+5<used;i++)if(!memcmp(response+i,"\\u0000",6))return false;
 cJSON *result=cJSON_ParseWithOpts(response,NULL,true);
 cJSON *text=cJSON_GetObjectItemCaseSensitive(result,"recognizedText"),*binding=cJSON_GetObjectItemCaseSensitive(result,"session"),*sequence=cJSON_GetObjectItemCaseSensitive(result,"sequence");
 bool recognized=cJSON_IsObject(result)&&cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(result,"recognized"))&&
  cJSON_IsString(text)&&strlen(text->valuestring)>0&&strlen(text->valuestring)<=480&&
  cJSON_IsString(binding)&&!strcmp(binding->valuestring,session)&&cJSON_IsNumber(sequence)&&sequence->valuedouble==1;
 if(recognized){
  for(const unsigned char *p=(const unsigned char *)text->valuestring;*p;p++)if(*p<32||*p==127)recognized=false;
 }
 bool current=live(epoch);
 taskENTER_CRITICAL(&result_lock);
 if(recognized&&current&&atomic_load(&generation)==epoch){memset(recognized_text,0,sizeof(recognized_text));memcpy(recognized_text,text->valuestring,strlen(text->valuestring));}
 else recognized=false;
 taskEXIT_CRITICAL(&result_lock);
 cJSON_Delete(result);return recognized;
}
static void recorder(void *context){
 unsigned epoch=atomic_load(&generation);uint8_t nonce[8];char session[17];
 esp_fill_random(nonce,sizeof(nonce));amoled_hex(nonce,sizeof(nonce),session);
 uint8_t *pcm=heap_caps_malloc(320000,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
 pc_audio_take take;pc_audio_take_init(&take);
 bool opened=false,recorded=false;
 int16_t block[256];uint64_t began=(uint64_t)esp_timer_get_time()/1000;
 if(!pcm||!live(epoch)||!atomic_load(&held))goto done;
 if(!microphone_open())goto done;
 opened=true;atomic_store(&stage,1);began=(uint64_t)esp_timer_get_time()/1000;pc_audio_take_begin(&take,epoch,began);
 while(atomic_load(&held)&&live(epoch)&&take.bytes<320000){
  /* A short block bounds normal capture latency. Recheck epoch after the
   * codec's blocking read: late DMA data never survives STOP or network loss. */
  if(esp_codec_dev_read(microphone,block,sizeof(block))!=ESP_CODEC_DEV_OK)goto done;
  if(!live(epoch))goto done;
  /* RELEASE may happen during the blocking read. Discard that whole
   * crossing block, but keep previously completed samples for recognition. */
  if(!atomic_load(&held)){memset(block,0,sizeof(block));break;}
  uint64_t energy=0;
  for(unsigned i=0;i<256;i++)energy+=(int64_t)block[i]*block[i];
  unsigned rms=(unsigned)sqrt((double)energy/256);
  if(!pc_audio_take_append(&take,epoch,(uint64_t)esp_timer_get_time()/1000,sizeof(block),rms))goto done;
  memcpy(pcm+take.bytes-sizeof(block),block,sizeof(block));atomic_store(&duration,take.bytes/32);
 }
 recorded=live(epoch)&&pc_audio_take_finish(&take);
 if(opened){esp_codec_dev_close(microphone);opened=false;}amplifier_off();
 if(recorded){atomic_store(&stage,2);bool recognized=upload(pcm,take.bytes,epoch,session,false);atomic_store(&stage,recognized?3:4);}
 else if(live(epoch))atomic_store(&stage,4);
 done:
 if(opened)esp_codec_dev_close(microphone);
 amplifier_off();memset(block,0,sizeof(block));
 if(pcm){memset(pcm,0,320000);heap_caps_free(pcm);}
 if(atomic_load(&generation)!=epoch){upload(NULL,0,epoch,session,true);atomic_store(&stage,5);}
 else if(atomic_load(&stage)==0||atomic_load(&stage)==1)atomic_store(&stage,4);
 atomic_store(&held,false);amoled_relay_audio_release();atomic_store(&busy,false);vTaskDelete(NULL);
}
static bool reserve_audio(void){return !amoled_ota_busy()&&amoled_relay_audio_acquire();}
bool amoled_audio_press(void){
 bool expected=false;
 if(!amoled_identity_ready()||!amoled_wifi_connected()||amoled_usb_armed()||amoled_ota_busy()||
    !atomic_compare_exchange_strong(&busy,&expected,true))return false;
 if(!amoled_usb_reserve_ota(reserve_audio)){atomic_store(&busy,false);return false;}
 clear_result();atomic_fetch_add(&generation,1);atomic_store(&held,true);atomic_store(&duration,0);atomic_store(&stage,0);
 if(xTaskCreate(recorder,"amoled_audio",8192,NULL,3,NULL)!=pdPASS){
  atomic_store(&held,false);amoled_relay_audio_release();atomic_store(&busy,false);atomic_store(&stage,4);return false;
 }
 return true;
}
