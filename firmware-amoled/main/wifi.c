#include "wifi.h"
#include "direct.h"
#include "audio.h"
#include "plugin.h"
#include "wifi_policy.h"
#include "esp_app_desc.h"
#include "version_policy.h"
#include "usb.h"
#include "identity.h"
#include "relay.h"
#include "ota_ble.h"
#include <stdatomic.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include "cJSON.h"
#include "nvs.h"
#include "esp_wifi.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include "esp_netif_sntp.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"

typedef struct {uint32_t schema;char ssid[33],password[64],endpoint[191];} PrivateConfig;
typedef struct {uint32_t schema;char ssid[33],password[64],endpoint[191];char backup_ssid[33],backup_password[64];uint32_t automatic;} MultiConfig;
static MultiConfig config;
static bool automatic_download;
static atomic_bool auto_enabled;
static SemaphoreHandle_t mutex;
static atomic_bool configured,connected,requested,transfer,ready;
static bool runtime_started,runtime_attempted;
static esp_err_t runtime_error=ESP_ERR_INVALID_STATE;
static esp_err_t runtime_start(void);
static atomic_uint generation=1,config_generation=1,requested_epoch,stage;
static const char *field(cJSON *o,const char *name){
 cJSON *v=cJSON_GetObjectItemCaseSensitive(o,name);
 return cJSON_IsString(v)?v->valuestring:"";
}
bool amoled_wifi_configured(void){return atomic_load(&configured);}
bool amoled_wifi_connected(void){return atomic_load(&connected);}
unsigned amoled_wifi_ota_stage(void){return atomic_load(&stage);}
bool amoled_wifi_transferring(void){return atomic_load(&transfer);}
void amoled_wifi_cancel(void){
 amoled_plugin_cancel();amoled_audio_cancel();
 amoled_direct_cancel();
 atomic_fetch_add(&generation,1);atomic_store(&requested,false);
 if(atomic_load(&transfer))amoled_ota_cancel();
}
static bool allowed(void){
 return atomic_load(&ready)&&!amoled_relay_audio_owned()&&!amoled_relay_direct_owned()&&!atomic_load(&requested)&&!atomic_load(&transfer)&&
  pc_wifi_maintenance_allowed(amoled_usb_ready(),amoled_usb_armed(),amoled_ota_busy(),amoled_relay_connected());
}
static bool configure(void *context){
 cJSON *o=context;const char *op=field(o,"op");
 if(!allowed())return false;
 bool clear=!strcmp(op,"maintenance.wifi.clear");
 MultiConfig next={.schema=2};
 if(!clear){
  const char *ssid=field(o,"ssid"),*password=field(o,"password"),*endpoint=field(o,"endpoint");
  if(!pc_wifi_config_valid(ssid,password,endpoint))return false;
  const char *backup=field(o,"backupSsid"),*backup_password=field(o,"backupPassword");
  cJSON *automatic=cJSON_GetObjectItemCaseSensitive(o,"autoUpdate");
  bool multi=backup[0]||backup_password[0]||automatic;
  if(multi&&(!pc_wifi_config_valid(backup,backup_password,endpoint)||!cJSON_IsBool(automatic)))return false;
  if(multi){strcpy(next.backup_ssid,backup);strcpy(next.backup_password,backup_password);next.automatic=cJSON_IsTrue(automatic);}
  memcpy(next.ssid,ssid,strlen(ssid));memcpy(next.password,password,strlen(password));memcpy(next.endpoint,endpoint,strlen(endpoint));
 }
 nvs_handle_t storage;
 if(nvs_open("controller-wifi",NVS_READWRITE,&storage)!=ESP_OK){memset(&next,0,sizeof(next));return false;}
 esp_err_t e=clear?nvs_erase_key(storage,"config"):nvs_set_blob(storage,"config",&next,sizeof(next));
 if(clear&&e==ESP_ERR_NVS_NOT_FOUND)e=ESP_OK;
 if(e==ESP_OK)e=nvs_commit(storage);
 nvs_close(storage);
 if(e==ESP_OK&&xSemaphoreTake(mutex,pdMS_TO_TICKS(100))==pdTRUE){
  config=next;atomic_store(&auto_enabled,next.automatic!=0);atomic_store(&configured,!clear);atomic_fetch_add(&config_generation,1);
  xSemaphoreGive(mutex);amoled_wifi_cancel();
 }else e=ESP_FAIL;
 memset(&next,0,sizeof(next));
 if(e==ESP_OK&&!clear)e=runtime_start();
 return e==ESP_OK;
}
static bool request_ota(void *unused){
 if(!allowed()||!amoled_identity_ready()||!atomic_load(&configured)||!atomic_load(&connected))return false;
 atomic_store(&requested_epoch,atomic_load(&generation));
 atomic_store(&requested,true);atomic_store(&stage,1);return true;
}
bool amoled_wifi_console(cJSON *o){
 const char *op=field(o,"op");
 bool setup=!strcmp(op,"maintenance.wifi.configure"),clear=!strcmp(op,"maintenance.wifi.clear"),ota=!strcmp(op,"maintenance.wifi.ota");
 if(!setup&&!clear&&!ota)return false;
 bool fields=setup?(cJSON_GetArraySize(o)==5||cJSON_GetArraySize(o)==8):cJSON_GetArraySize(o)==2;
 bool accepted=fields&&!strcmp(field(o,"device"),amoled_usb_serial())&&
  amoled_usb_maintenance(ota?request_ota:configure,o);
 cJSON *response=cJSON_CreateObject();
 cJSON_AddStringToObject(response,"result",accepted?(ota?"wifi-ota-requested":"wifi-config-saved"):"wifi-maintenance-rejected");
 cJSON_AddBoolToObject(response,"wifiConfigured",amoled_wifi_configured());
 cJSON_AddBoolToObject(response,"wifiConnected",amoled_wifi_connected());
 cJSON_AddBoolToObject(response,"autoUpdate",atomic_load(&auto_enabled));
 char *text=cJSON_PrintUnformatted(response);cJSON_Delete(response);
 if(text){amoled_usb_write(text);amoled_usb_write("\n");free(text);}
 return true;
}
static void wifi_event(void *unused,esp_event_base_t base,int32_t id,void *data){
 if(base==IP_EVENT&&id==IP_EVENT_STA_GOT_IP)atomic_store(&connected,true);
 if(base==WIFI_EVENT&&id==WIFI_EVENT_STA_DISCONNECTED){
  atomic_store(&connected,false);amoled_wifi_cancel();
 }
}
static bool live(unsigned epoch){
 return atomic_load(&generation)==epoch&&atomic_load(&connected)&&(atomic_load(&transfer)||!amoled_relay_connected());
}
static void close_http(esp_http_client_handle_t client){
 if(client){esp_http_client_close(client);esp_http_client_cleanup(client);}
}
static esp_http_client_handle_t open_http(const char *endpoint,const char *path,unsigned epoch,int *length){
 if(!live(epoch)||time(NULL)<1700000000)return NULL; /* Never skip certificate time validation. */
 char url[320];int n=snprintf(url,sizeof(url),"%s%s",endpoint,path);
 if(n<0||n>=(int)sizeof(url))return NULL;
 esp_http_client_config_t cfg={.url=url,.timeout_ms=5000,.crt_bundle_attach=esp_crt_bundle_attach,
  .disable_auto_redirect=true,.buffer_size=2048,.keep_alive_enable=false};
 esp_http_client_handle_t client=esp_http_client_init(&cfg);
 if(!client)return NULL;
 if(amoled_identity_http_auth(client)!=ESP_OK||esp_http_client_set_header(client,"Connection","close")!=ESP_OK||
    esp_http_client_open(client,0)!=ESP_OK||!live(epoch)){close_http(client);return NULL;}
 int64_t bytes=esp_http_client_fetch_headers(client);
 if(bytes<1||bytes>0x600000||esp_http_client_get_status_code(client)!=200||
    esp_http_client_is_chunked_response(client)||!live(epoch)){close_http(client);return NULL;}
 *length=(int)bytes;return client;
}
static void download(const char *endpoint,unsigned epoch){
 char manifest[193]={0},sha[65],version[32];uint8_t digest[32],block[511];
 int length=0;uint32_t total=0,received=0;unsigned ota_epoch=0;bool begun=false,ok=false;
 int64_t deadline=esp_timer_get_time()+120000000;
 esp_http_client_handle_t client=open_http(endpoint,"/firmware/manifest",epoch,&length);
 if(!client||length>192)goto done;
 int used=0;
 while(used<length&&live(epoch)&&esp_timer_get_time()<deadline){
  int count=esp_http_client_read(client,manifest+used,length-used);
  if(count<=0)goto done;
  used+=count;
 }
 if(used!=length||!esp_http_client_is_complete_data_received(client)||
    !pc_wifi_manifest(manifest,length,&total,sha,version)||!amoled_unhex(sha,32,digest))goto done;
 close_http(client);client=NULL;
 if(automatic_download&&!amoled_release_newer(version,esp_app_get_description()->version)){
  atomic_store(&stage,0);ok=true;goto done;
 }
 if(!live(epoch)||esp_timer_get_time()>=deadline||!amoled_ota_wifi_begin(version,total,digest,(uint64_t)deadline/1000,&ota_epoch))goto done;
 begun=true;atomic_store(&stage,2);
 char path[112];snprintf(path,sizeof(path),"/firmware/image?sha=%s",sha);
 client=open_http(endpoint,path,epoch,&length);
 if(!client||(uint32_t)length!=total)goto done;
 while(received<total&&live(epoch)&&amoled_ota_wifi_live(ota_epoch)&&esp_timer_get_time()<deadline){
  size_t want=total-received;if(want>sizeof(block))want=sizeof(block);
  int count=esp_http_client_read(client,(char *)block,want);
  if(count<=0||!live(epoch)||!amoled_ota_wifi_live(ota_epoch)||esp_timer_get_time()>=deadline)goto done;
  /* Queue congestion fails closed. Chunks are never retried or resumed. */
  if(!amoled_ota_wifi_chunk(ota_epoch,block,count,false))goto done;
  received+=count;
 }
 if(received!=total||!live(epoch)||esp_timer_get_time()>=deadline||!esp_http_client_is_complete_data_received(client))goto done;
 close_http(client);client=NULL;
 if(!live(epoch)||esp_timer_get_time()>=deadline||!amoled_ota_wifi_chunk(ota_epoch,NULL,0,true))goto done;
 atomic_store(&stage,3); /* Queued for verification, not successful installation. */
 while(live(epoch)&&esp_timer_get_time()<deadline){
  uint8_t status[4];amoled_ota_status(status);
  if(status[0]==3){ok=true;break;}
  if(status[0]==4||!amoled_ota_wifi_live(ota_epoch))break;
  vTaskDelay(pdMS_TO_TICKS(20));
 }
 done:
 close_http(client);memset(block,0,sizeof(block));memset(digest,0,sizeof(digest));
 if(!ok){if(begun)amoled_ota_cancel();atomic_store(&stage,4);}
}
static void worker(void *unused){
 unsigned seen=0,profile=0;int64_t retry=0,auto_check=esp_timer_get_time()+60000000;
 for(;;){
  unsigned next=atomic_load(&config_generation);
  if(seen!=next){
   MultiConfig snapshot={0};
   xSemaphoreTake(mutex,portMAX_DELAY);snapshot=config;xSemaphoreGive(mutex);
   profile=0;esp_wifi_disconnect();atomic_store(&connected,false);
   if(atomic_load(&configured)){
    esp_wifi_start();
    wifi_config_t settings={0};memcpy(settings.sta.ssid,snapshot.ssid,strlen(snapshot.ssid));
    memcpy(settings.sta.password,snapshot.password,strlen(snapshot.password));
    settings.sta.threshold.authmode=WIFI_AUTH_WPA2_PSK;settings.sta.pmf_cfg.capable=true;
    if(esp_wifi_set_config(WIFI_IF_STA,&settings)==ESP_OK)esp_wifi_connect();
    memset(&settings,0,sizeof(settings));
   }else esp_wifi_stop();
   memset(&snapshot,0,sizeof(snapshot));seen=next;retry=esp_timer_get_time()+10000000;
  }
  if(atomic_load(&configured)&&!atomic_load(&connected)&&esp_timer_get_time()>=retry){
   MultiConfig snapshot={0};
   xSemaphoreTake(mutex,portMAX_DELAY);snapshot=config;xSemaphoreGive(mutex);
   if(snapshot.backup_ssid[0])profile^=1;
   wifi_config_t settings={0};
   const char *ssid=profile?snapshot.backup_ssid:snapshot.ssid;
   memcpy(settings.sta.ssid,ssid,strlen(ssid));
   const char *password=profile?snapshot.backup_password:snapshot.password;
   memcpy(settings.sta.password,password,strlen(password));
   settings.sta.threshold.authmode=WIFI_AUTH_WPA2_PSK;settings.sta.pmf_cfg.capable=true;
   esp_wifi_disconnect();
   if(esp_wifi_set_config(WIFI_IF_STA,&settings)==ESP_OK)esp_wifi_connect();
   memset(&snapshot,0,sizeof(snapshot));memset(&settings,0,sizeof(settings));
   retry=esp_timer_get_time()+15000000;
  }
  if(atomic_load(&requested)){
   atomic_store(&transfer,true);
   bool perform=atomic_exchange(&requested,false);
   char endpoint[191];xSemaphoreTake(mutex,portMAX_DELAY);memcpy(endpoint,config.endpoint,sizeof(endpoint));xSemaphoreGive(mutex);
   automatic_download=false;
   if(perform)download(endpoint,atomic_load(&requested_epoch));
   memset(endpoint,0,sizeof(endpoint));atomic_store(&transfer,false);
  }
  if(atomic_load(&auto_enabled)&&atomic_load(&connected)&&time(NULL)>=1700000000&&
     esp_timer_get_time()>=auto_check&&!amoled_usb_armed()&&!amoled_ota_busy()&&
     !amoled_relay_connected()&&!amoled_relay_audio_owned()&&!amoled_relay_direct_owned()&&amoled_identity_ready()){
   char endpoint[191];xSemaphoreTake(mutex,portMAX_DELAY);memcpy(endpoint,config.endpoint,sizeof(endpoint));xSemaphoreGive(mutex);
   auto_check=esp_timer_get_time()+600000000; /* At most once per five minutes, including failures/STOP. */
   atomic_store(&transfer,true);atomic_store(&stage,1);automatic_download=true;
   download(endpoint,atomic_load(&generation));
   automatic_download=false;atomic_store(&transfer,false);memset(endpoint,0,sizeof(endpoint));
  }
  vTaskDelay(pdMS_TO_TICKS(100));
 }
}
esp_err_t amoled_wifi_start(void){
 mutex=xSemaphoreCreateMutex();if(!mutex)return ESP_ERR_NO_MEM;
 nvs_handle_t storage;size_t size=sizeof(config);
 if(nvs_open("controller-wifi",NVS_READONLY,&storage)==ESP_OK){
  esp_err_t loaded=nvs_get_blob(storage,"config",&config,&size);
  bool legacy=loaded==ESP_OK&&size==sizeof(PrivateConfig)&&config.schema==1;
  bool multi=loaded==ESP_OK&&size==sizeof(config)&&config.schema==2&&config.automatic<=1&&memchr(config.endpoint,0,sizeof(config.endpoint))&&
    memchr(config.backup_ssid,0,sizeof(config.backup_ssid))&&memchr(config.backup_password,0,sizeof(config.backup_password))&&
    (!config.backup_ssid[0]||pc_wifi_config_valid(config.backup_ssid,config.backup_password,config.endpoint));
  if((legacy||multi)&&memchr(config.ssid,0,sizeof(config.ssid))&&memchr(config.password,0,sizeof(config.password))&&
    memchr(config.endpoint,0,sizeof(config.endpoint))&&pc_wifi_config_valid(config.ssid,config.password,config.endpoint)){
   atomic_store(&configured,true);atomic_store(&auto_enabled,multi&&config.automatic);
  }else memset(&config,0,sizeof(config));
  nvs_close(storage);
 }
 atomic_store(&ready,true);
 /* Unconfigured boards allocate no Wi-Fi/LwIP/SNTP state or worker stack. */
 return atomic_load(&configured)?runtime_start():ESP_OK;
}

static esp_err_t runtime_initialize(void){
 esp_err_t err=esp_netif_init();if(err!=ESP_OK)return err;
 err=esp_event_loop_create_default();if(err!=ESP_OK&&err!=ESP_ERR_INVALID_STATE)return err;
 if(!esp_netif_create_default_wifi_sta())return ESP_ERR_NO_MEM;
 wifi_init_config_t cfg=WIFI_INIT_CONFIG_DEFAULT();
 err=esp_wifi_init(&cfg);if(err!=ESP_OK)return err;
 if((err=esp_wifi_set_storage(WIFI_STORAGE_RAM))!=ESP_OK)return err;
 if((err=esp_wifi_set_mode(WIFI_MODE_STA))!=ESP_OK)return err;
 if((err=esp_event_handler_register(WIFI_EVENT,ESP_EVENT_ANY_ID,wifi_event,NULL))!=ESP_OK)return err;
 if((err=esp_event_handler_register(IP_EVENT,IP_EVENT_STA_GOT_IP,wifi_event,NULL))!=ESP_OK)return err;
 esp_sntp_config_t sntp=ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
 if((err=esp_netif_sntp_init(&sntp))!=ESP_OK)return err;
 if(xTaskCreate(worker,"amoled_wifi",8192,NULL,3,NULL)!=pdPASS)return ESP_ERR_NO_MEM;
 if((err=amoled_direct_start())!=ESP_OK)return err;
 runtime_started=true;return ESP_OK;
}

/* A partial IDF startup is not repeated into duplicate netifs/event handlers.
 * A saved configuration remains private; maintenance restart can retry startup. */
static esp_err_t runtime_start(void){
 if(runtime_started)return ESP_OK;
 if(runtime_attempted)return runtime_error;
 runtime_attempted=true;runtime_error=runtime_initialize();return runtime_error;
}

bool amoled_wifi_endpoint(char *out,size_t size){
 if(!out||size<sizeof(config.endpoint)||!mutex||!amoled_wifi_configured())return false;
 if(xSemaphoreTake(mutex,pdMS_TO_TICKS(100))!=pdTRUE)return false;
 memcpy(out,config.endpoint,sizeof(config.endpoint));xSemaphoreGive(mutex);return true;
}
