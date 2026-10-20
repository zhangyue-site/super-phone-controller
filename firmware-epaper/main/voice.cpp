#include "voice.h"
#include <atomic>
#include <string.h>
#include <math.h>
#include "esp_random.h"
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
static std::atomic<bool> diagnostic(false);
static TaskHandle_t worker;
static esp_codec_dev_handle_t mic;
static bool attempted=false;
static char session[17];
static std::atomic<unsigned> next_sequence(1),record_sequence(0),cancel_sequence(0);
static void state(int value){stage=value;controller_voice_changed(false);}
static bool init_mic(){
 if(attempted)return mic!=nullptr;
 attempted=true;
 i2c_master_bus_config_t buscfg={};buscfg.i2c_port=I2C_NUM_0;buscfg.sda_io_num=GPIO_NUM_47;buscfg.scl_io_num=GPIO_NUM_48;
 buscfg.clk_source=I2C_CLK_SRC_DEFAULT;buscfg.glitch_ignore_cnt=7;buscfg.flags.enable_internal_pullup=true;
 i2c_master_bus_handle_t bus;
 if(i2c_new_master_bus(&buscfg,&bus)!=ESP_OK)return false;
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
 es8311_codec_cfg_t codec={};codec.ctrl_if=ctrl;codec.gpio_if=audio_codec_new_gpio();codec.codec_mode=ESP_CODEC_DEV_WORK_MODE_ADC;
 codec.pa_pin=-1;codec.use_mclk=true;
 auto cif=es8311_codec_new(&codec);
 audio_codec_i2s_cfg_t datacfg={};datacfg.port=0;datacfg.rx_handle=rx;datacfg.tx_handle=tx;
 auto data=audio_codec_new_i2s_data(&datacfg);
 if(!cif || !data)return false;
 esp_codec_dev_cfg_t dev={};dev.dev_type=ESP_CODEC_DEV_TYPE_IN;dev.codec_if=cif;dev.data_if=data;
 mic=esp_codec_dev_new(&dev);if(!mic)return false;
 ESP_LOGI("voice","ES8311 driver initialized; ADC remains closed until hold");return true;
}
static void run(void*){
 auto pcm=(int16_t*)heap_caps_malloc(320000,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
 for(;;){
  ulTaskNotifyTake(pdTRUE,portMAX_DELAY);
  bool test=diagnostic.exchange(false);
  if((!held || cancelled) && !test)continue;
  if(!test && !controller_voice_online()){state(6);continue;}
  if(!pcm || !init_mic()){state(5);continue;}
  unsigned sequence=record_sequence.load();
  state(4);unsigned count=0;int16_t stereo[512];
  esp_codec_dev_sample_info_t fs={};fs.sample_rate=16000;fs.channel=2;fs.bits_per_sample=16;
  if(esp_codec_dev_open(mic,&fs)!=ESP_CODEC_DEV_OK){state(5);continue;}
  esp_codec_dev_set_in_gain(mic,30.0);
  // Every open restarts RX and resets its DMA queue; no pre-hold audio survives.
  // Discard codec startup transients while the local recording indicator prepares.
  bool warmed=true;
  for(int i=0;i<64 && !cancelled && (test || held);++i){
   if(esp_codec_dev_read(mic,stereo,sizeof(stereo))!=ESP_CODEC_DEV_OK){warmed=false;break;}
  }
  state(1);
  bool ok=warmed;
  while(ok && (test || held) && !cancelled && count<(test?16000u:160000u)){
   if(esp_codec_dev_read(mic,stereo,sizeof(stereo))!=ESP_CODEC_DEV_OK){ok=false;break;}
   if(cancelled || (!test && !held))break;
   for(unsigned i=0;i<256 && count<(test?16000u:160000u);++i)pcm[count++]=stereo[i*2];
  }
  esp_codec_dev_close(mic);
  if(test){
   double squares=0;int peak=0;for(unsigned i=0;i<count;++i){int value=pcm[i];squares+=(double)value*value;if(abs(value)>peak)peak=abs(value);}
   ESP_LOGI("voice","MIC TEST samples=%u rms=%.1f peak=%d; audio discarded, no upload",count,count?sqrt(squares/count):0,peak);
   state(ok?0:5);continue;
  }
  if(cancelled){state(0);continue;}
  if(!ok || count<6400){state(5);continue;}
  state(2);
  bool uploaded=controller_voice_upload((unsigned char*)pcm,count*2,sequence);
  if(cancelled){state(0);continue;}
  state(uploaded?3:5);if(uploaded)controller_voice_changed(true);
 }
}
void controller_voice_init(){snprintf(session,sizeof(session),"%08x%08x",(unsigned)esp_random(),(unsigned)esp_random());xTaskCreate(run,"voice",6144,nullptr,4,&worker);}
void controller_voice_hold(bool value){
 if(!value){held=false;return;}
 if(stage==1 || stage==2 || stage==4)return;
 record_sequence=next_sequence.fetch_add(1);cancelled=false;held=true;xTaskNotifyGive(worker);
}
void controller_voice_cancel(){cancel_sequence=next_sequence.fetch_add(1);cancelled=true;held=false;}
int controller_voice_stage(){return stage.load();}

void controller_voice_test(){if(stage==1||stage==2||stage==4)return;cancelled=false;diagnostic=true;xTaskNotifyGive(worker);}

const char *controller_voice_session(){return session;}
unsigned controller_voice_cancel_sequence(){return cancel_sequence.load();}
