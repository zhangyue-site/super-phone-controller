#include "voice.h"
#include "touch.h"
#include "adb_local.h"
#include "sdkconfig.h"
#include <atomic>
#include <string.h>
#include <math.h>
#include "esp_random.h"
#include "nvs.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_codec_dev.h"
#include "esp_codec_dev_defaults.h"
#include "driver/i2c_master.h"
#include "driver/i2s_std.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
static std::atomic<bool> held(false),cancelled(false);
static std::atomic<int> stage(0);
static std::atomic<uint32_t> adb_consent(0);
static std::atomic<bool> diagnostic(false),prepare_only(false);
static TaskHandle_t worker,stream_worker;
static VoiceStream stream;
static void upload_run(void*){
 for(;;){ulTaskNotifyTake(pdTRUE,portMAX_DELAY);bool ok=controller_voice_stream_upload(stream);stream.result=ok?1:-1;}
}
static esp_codec_dev_handle_t mic;
static std::atomic<int> output_volume(60),pending_prompt(0);
static std::atomic<bool> output_muted(false);
static std::atomic<unsigned> playback_epoch(0);
#define AUDIO_ASSET(name) extern const uint8_t name##_start[] asm("_binary_" #name "_pcm_start"); extern const uint8_t name##_end[] asm("_binary_" #name "_pcm_end");
AUDIO_ASSET(ready)
AUDIO_ASSET(recognized)
AUDIO_ASSET(failed)
AUDIO_ASSET(stopped)
AUDIO_ASSET(test)
static void save_audio(){
 nvs_handle_t h;if(nvs_open("audio",NVS_READWRITE,&h)!=ESP_OK)return;
 nvs_set_u8(h,"volume",output_volume.load());nvs_set_u8(h,"muted",output_muted.load());nvs_commit(h);nvs_close(h);
}
void controller_audio_interrupt(){playback_epoch.fetch_add(1);pending_prompt=0;}
int controller_audio_volume(){return output_volume.load();}
bool controller_audio_muted(){return output_muted.load();}
void controller_audio_adjust(int delta){output_volume=controller::clamp_volume(output_volume.load()+delta);save_audio();}
void controller_audio_toggle_mute(){output_muted=!output_muted.load();controller_audio_interrupt();save_audio();}
void controller_audio_prompt(controller::SpeechPrompt value){
 if(output_muted || output_volume==0 || held)return;
 pending_prompt=(int)value;if(worker)xTaskNotifyGive(worker);
}

static bool attempted=false;
static char session[17];
static std::atomic<unsigned> next_sequence(1),record_sequence(0),cancel_sequence(0);
static void state(int value){stage=value;controller_voice_changed(false);}
static bool init_mic(){
 if(attempted)return mic!=nullptr;
 attempted=true;
 // V2 PA_EN is an active-low P-MOS supply for both ES8311 and amplifier.
 gpio_set_level(GPIO_NUM_42,0);vTaskDelay(pdMS_TO_TICKS(20));
 i2c_master_bus_handle_t bus=controller_i2c_bus();
 if(!bus)return false;
 if(i2c_master_probe(bus,0x18,100)!=ESP_OK){ESP_LOGW("voice","ES8311 not responding");return false;}
 i2s_chan_handle_t tx,rx;
 i2s_chan_config_t channel=I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0,I2S_ROLE_MASTER);
 if(i2s_new_channel(&channel,&tx,&rx)!=ESP_OK)return false;
 i2s_std_config_t cfg={};cfg.clk_cfg=I2S_STD_CLK_DEFAULT_CONFIG(16000);
 cfg.slot_cfg=I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT,I2S_SLOT_MODE_STEREO);
 cfg.gpio_cfg.mclk=GPIO_NUM_14;cfg.gpio_cfg.bclk=GPIO_NUM_15;cfg.gpio_cfg.ws=GPIO_NUM_38;
 cfg.gpio_cfg.dout=GPIO_NUM_45;cfg.gpio_cfg.din=GPIO_NUM_16;
 if(i2s_channel_init_std_mode(tx,&cfg)!=ESP_OK || i2s_channel_init_std_mode(rx,&cfg)!=ESP_OK)return false;
 audio_codec_i2c_cfg_t ctrlcfg={};ctrlcfg.port=0;ctrlcfg.addr=ES8311_CODEC_DEFAULT_ADDR;ctrlcfg.bus_handle=bus;
 auto ctrl=audio_codec_new_i2c_ctrl(&ctrlcfg);
 es8311_codec_cfg_t codec={};codec.ctrl_if=ctrl;codec.gpio_if=audio_codec_new_gpio();codec.codec_mode=ESP_CODEC_DEV_WORK_MODE_BOTH;
 codec.pa_pin=46;codec.hw_gain.pa_gain=6.0;codec.hw_gain.pa_voltage=3.3;codec.hw_gain.codec_dac_voltage=3.3;codec.use_mclk=true;
 auto cif=es8311_codec_new(&codec);
 audio_codec_i2s_cfg_t datacfg={};datacfg.port=0;datacfg.rx_handle=rx;datacfg.tx_handle=tx;
 auto data=audio_codec_new_i2s_data(&datacfg);
 if(!cif || !data)return false;
 esp_codec_dev_cfg_t dev={};dev.dev_type=ESP_CODEC_DEV_TYPE_IN_OUT;dev.codec_if=cif;dev.data_if=data;
 mic=esp_codec_dev_new(&dev);if(!mic)return false;
 ESP_LOGI("voice","ES8311 driver initialized; ADC remains closed until hold");return true;
}
static void play_prompt(int prompt){
 const uint8_t *starts[]={nullptr,ready_start,recognized_start,failed_start,stopped_start,test_start};
 const uint8_t *ends[]={nullptr,ready_end,recognized_end,failed_end,stopped_end,test_end};
 if(prompt<1||prompt>5||output_muted||held||!init_mic())return;
 unsigned epoch=playback_epoch.load();
 esp_codec_dev_sample_info_t fs={};fs.sample_rate=16000;fs.channel=2;fs.bits_per_sample=16;
 if(esp_codec_dev_open(mic,&fs)!=ESP_CODEC_DEV_OK)return;
 esp_codec_dev_set_out_mute(mic,false);
 int16_t stereo[512];const uint8_t *cursor=starts[prompt];
 while(cursor<ends[prompt]&&!held&&!output_muted&&epoch==playback_epoch.load()){
  size_t n=(ends[prompt]-cursor)/2;if(n>256)n=256;
  if(!n)break;
  for(size_t i=0;i<n;++i){int16_t sample=(int16_t)(cursor[2*i]|(cursor[2*i+1]<<8));stereo[2*i]=sample;stereo[2*i+1]=sample;}
  esp_codec_dev_set_out_vol(mic,output_volume.load());
  if(esp_codec_dev_write(mic,stereo,n*4)!=ESP_CODEC_DEV_OK)break;
  cursor+=n*2;
 }
 esp_codec_dev_set_out_mute(mic,true);esp_codec_dev_close(mic);
}
static void run(void*){
 auto pcm=(int16_t*)heap_caps_malloc(320000,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
 for(;;){
  ulTaskNotifyTake(pdTRUE,portMAX_DELAY);
  int prompt=pending_prompt.exchange(0);
  if(prompt && !held){play_prompt(prompt);continue;}
  bool test=diagnostic.exchange(false);
  bool prepare=prepare_only.exchange(false);
  if((!held || cancelled) && !test)continue;
#if CONFIG_CONTROLLER_USB_LOCAL
  if(!test && (prepare || !controller_voice_prepared())){
   unsigned cancel_at_start=cancel_sequence.load();uint32_t consent=adb_consent.load();
   if(cancelled)continue;
   state(7);bool ready=controller_adb_activate(consent);
   if(ready && !cancelled && controller_voice_online())ready=controller_preflight_probe();
   if(!cancelled && cancel_sequence.load()==cancel_at_start){state(ready?8:9);held=false;if(ready&&controller_voice_prepared())controller_audio_prompt(controller::SpeechPrompt::READY);}
   continue;
  }
#endif
  if(!test && prepare){state(6);held=false;continue;}
  if(!test && !controller_voice_online()){state(6);continue;}
  if(!pcm || !init_mic()){state(5);continue;}
  unsigned sequence=record_sequence.load();
  state(4);unsigned count=0;int16_t stereo[512];
  esp_codec_dev_sample_info_t fs={};fs.sample_rate=16000;fs.channel=2;fs.bits_per_sample=16;
  if(esp_codec_dev_open(mic,&fs)!=ESP_CODEC_DEV_OK){state(5);continue;}
  esp_codec_dev_set_out_mute(mic,true);
  esp_codec_dev_set_in_gain(mic,30.0);
  if(!test){
   stream.pcm=(unsigned char*)pcm;stream.bytes=0;stream.done=false;stream.abort=false;stream.result=0;stream.finished_at=0;stream.sequence=sequence;
   xTaskNotifyGive(stream_worker);
  }
  // Every open restarts RX and resets its DMA queue; no pre-hold audio survives.
  // Discard codec startup transients while the local recording indicator prepares.
  bool warmed=true;
  for(int i=0;i<8 && !cancelled && (test || held);++i){
   if(esp_codec_dev_read(mic,stereo,sizeof(stereo))!=ESP_CODEC_DEV_OK){warmed=false;break;}
  }
  state(1);
  bool ok=warmed;
  while(ok && (test || held) && !cancelled && count<(test?16000u:160000u)){
   if(esp_codec_dev_read(mic,stereo,sizeof(stereo))!=ESP_CODEC_DEV_OK){ok=false;break;}
   if(cancelled || (!test && !held))break;
   for(unsigned i=0;i<256 && count<(test?16000u:160000u);++i)pcm[count++]=stereo[i*2];
   if(!test){stream.bytes=count*2;if(stream.result<0){ok=false;break;}}
  }
  esp_codec_dev_close(mic);
  if(test){
   double squares=0;int peak=0;for(unsigned i=0;i<count;++i){int value=pcm[i];squares+=(double)value*value;if(abs(value)>peak)peak=abs(value);}
   ESP_LOGI("voice","MIC TEST samples=%u rms=%.1f peak=%d; audio discarded, no upload",count,count?sqrt(squares/count):0,peak);
   state(ok?0:5);continue;
  }
  stream.finished_at=esp_timer_get_time();stream.abort=cancelled||!ok||count<6400;stream.done=true;
  if(!stream.abort)state(2);
  while(stream.result==0){if(cancelled)stream.abort=true;vTaskDelay(pdMS_TO_TICKS(10));}
  if(cancelled){state(0);continue;}
  bool uploaded=stream.result==1;
  state(uploaded?3:5);if(uploaded)controller_voice_changed(true);
  controller_audio_prompt(uploaded?controller::SpeechPrompt::RECOGNIZED:controller::SpeechPrompt::FAILED);
 }
}
void controller_voice_init(){
 nvs_handle_t h;if(nvs_open("audio",NVS_READONLY,&h)==ESP_OK){uint8_t v=60,m=0;nvs_get_u8(h,"volume",&v);nvs_get_u8(h,"muted",&m);output_volume=controller::clamp_volume(v)/20*20;output_muted=m!=0;nvs_close(h);}
 snprintf(session,sizeof(session),"%08x%08x",(unsigned)esp_random(),(unsigned)esp_random());xTaskCreate(upload_run,"voice_stream",8192,nullptr,3,&stream_worker);xTaskCreate(run,"voice",6144,nullptr,4,&worker);}
static void begin_voice_request(){
 controller_audio_interrupt();
 adb_consent=controller_adb_ticket();record_sequence=next_sequence.fetch_add(1);cancelled=false;held=true;xTaskNotifyGive(worker);
}
void controller_voice_prepare(){
 if(stage==1 || stage==2 || stage==4 || stage==7)return;
 prepare_only=true;begin_voice_request();
}
void controller_voice_hold(bool value){
 if(!value){held=false;return;}
 if(stage==1 || stage==2 || stage==4 || stage==7)return;
 prepare_only=false;begin_voice_request();
}
void controller_voice_cancel(){controller_audio_interrupt();cancel_sequence=next_sequence.fetch_add(1);cancelled=true;held=false;}
int controller_voice_stage(){
#if CONFIG_CONTROLLER_USB_LOCAL
 if(stage>=7){int adb=controller_adb_stage();return adb==3?8:(adb==1||adb==2)?7:(adb==0?0:9);}
#endif
 return stage.load();
}

void controller_voice_test(){if(stage==1||stage==2||stage==4)return;controller_audio_interrupt();cancelled=false;diagnostic=true;xTaskNotifyGive(worker);}

const char *controller_voice_session(){return session;}
unsigned controller_voice_cancel_sequence(){return cancel_sequence.load();}
