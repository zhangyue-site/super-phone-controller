#include "identity.h"
#include "usb.h"
#include "relay.h"
#include "esp_mac.h"
#include "esp_random.h"
#include "esp_app_desc.h"
#include "nvs.h"
#include "mbedtls/md.h"
#include "cJSON.h"
#include "esp_http_client.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
static char serial[13],device[32],boot[33],secret[65];
static nvs_handle_t storage;
void amoled_hex(const uint8_t *data,size_t n,char *out){static const char h[]="0123456789abcdef";for(size_t i=0;i<n;i++){out[2*i]=h[data[i]>>4];out[2*i+1]=h[data[i]&15];}out[2*n]=0;}
static int hex_value(char c){return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:c>='A'&&c<='F'?c-'A'+10:-1;}
bool amoled_unhex(const char *text,size_t n,uint8_t *out){for(size_t i=0;i<n;i++){int a=hex_value(text[2*i]),b=hex_value(text[2*i+1]);if(a<0||b<0)return false;if(out)out[i]=(a<<4)|b;}return true;}
esp_err_t amoled_identity_init(void){
 uint8_t mac[6],nonce[16];esp_err_t e=esp_read_mac(mac,ESP_MAC_BASE);if(e!=ESP_OK)return e;
 snprintf(serial,sizeof(serial),"%02X%02X%02X%02X%02X%02X",mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
 char lower[13];amoled_hex(mac,6,lower);snprintf(device,sizeof(device),"amoled-%s",lower);
 esp_fill_random(nonce,sizeof(nonce));amoled_hex(nonce,sizeof(nonce),boot);
 e=nvs_open("controller-id",NVS_READWRITE,&storage);if(e!=ESP_OK)return e;
 size_t n=sizeof(secret);e=nvs_get_str(storage,"token",secret,&n);
 if(e==ESP_ERR_NVS_NOT_FOUND){secret[0]=0;return ESP_OK;}
 if(e!=ESP_OK||strlen(secret)!=64||!amoled_unhex(secret,32,NULL)){memset(secret,0,sizeof(secret));return ESP_ERR_INVALID_STATE;}return ESP_OK;
}
const char *amoled_identity_device(void){return device;}
const char *amoled_identity_serial(void){return serial;}
const char *amoled_identity_boot(void){return boot;}
bool amoled_identity_ready(void){return secret[0]!=0;}
esp_err_t amoled_identity_provision(const char *token){
 if(!token||strlen(token)!=64||!amoled_unhex(token,32,NULL)||amoled_usb_armed())return ESP_ERR_INVALID_ARG;
 if(secret[0])return strcmp(secret,token)==0?ESP_OK:ESP_ERR_INVALID_STATE;
 esp_err_t e=nvs_set_str(storage,"token",token);if(e==ESP_OK)e=nvs_commit(storage);if(e!=ESP_OK)return e;
 char check[65];size_t n=sizeof(check);e=nvs_get_str(storage,"token",check,&n);if(e!=ESP_OK||strcmp(check,token))return ESP_FAIL;
 memcpy(secret,check,sizeof(secret));memset(check,0,sizeof(check));return ESP_OK;
}
bool amoled_hmac(const uint8_t *key,size_t key_length,const void *data,size_t n,uint8_t out[32]){const mbedtls_md_info_t *md=mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);return md&&mbedtls_md_hmac(md,key,key_length,data,n,out)==0;}
bool amoled_identity_hmac(const void *data,size_t n,uint8_t out[32]){return amoled_identity_ready()&&amoled_hmac((const uint8_t*)secret,strlen(secret),data,n,out);}
bool amoled_control_console(const char *line){
 if(strncmp(line,"PCUSB ",6))return false;
 size_t length=strlen(line);if(length<43||line[38]!=' '||!amoled_unhex(line+6,16,NULL))return true;
 char request[33];memcpy(request,line+6,32);request[32]=0;
 cJSON *o=cJSON_CreateObject();if(!o)return true;
 cJSON_AddStringToObject(o,"device",device);cJSON_AddStringToObject(o,"usbSerial",serial);
 if(!strcmp(line+39,"INFO")){
  cJSON_AddNumberToObject(o,"protocol",1);cJSON_AddStringToObject(o,"version",esp_app_get_description()->version);
  cJSON_AddStringToObject(o,"boardModel","esp32-s3-touch-amoled-2.16");cJSON_AddStringToObject(o,"usbProfile","composite-fixed-v1");cJSON_AddBoolToObject(o,"provisioned",amoled_identity_ready());
 }else if(length==108&&!strncmp(line+39,"AUTH ",5)){
  uint8_t nonce[32],proof[32];char domain[128],encoded[65];int n=snprintf(domain,sizeof(domain),"pcusb-v1\n%s\n%s\n",device,serial);
  if(amoled_unhex(line+44,32,nonce)&&amoled_identity_ready()&&n>0&&n<(int)sizeof(domain)){
   uint8_t message[160];memcpy(message,domain,n);memcpy(message+n,nonce,32);
   if(amoled_identity_hmac(message,n+32,proof)){amoled_hex(proof,32,encoded);cJSON_AddStringToObject(o,"proof",encoded);}else cJSON_AddStringToObject(o,"error","signing_failed");
   memset(message,0,sizeof(message));memset(proof,0,sizeof(proof));
  }else cJSON_AddStringToObject(o,"error","not_provisioned_or_invalid_challenge");
  memset(nonce,0,sizeof(nonce));
 }else if(length==113&&!strncmp(line+39,"PROVISION ",10)){
  esp_err_t e=amoled_identity_provision(line+49);if(e==ESP_OK)e=amoled_relay_start();
  cJSON_AddStringToObject(o,"result",e==ESP_OK?"provisioned":"provisioning_rejected");
 }else cJSON_AddStringToObject(o,"error","unsupported");
 char *s=cJSON_PrintUnformatted(o);cJSON_Delete(o);if(s){char response[640];int n=snprintf(response,sizeof(response),"PCUSB %s %s\r\n",request,s);free(s);if(n>0&&n<(int)sizeof(response))amoled_usb_write(response);}return true;
}

esp_err_t amoled_identity_http_auth(void *client){
 if(!client||!amoled_identity_ready())return ESP_ERR_INVALID_STATE;
 char header[80];snprintf(header,sizeof(header),"Bearer %s",secret);
 esp_err_t e=esp_http_client_set_header((esp_http_client_handle_t)client,"Authorization",header);
 memset(header,0,sizeof(header));return e;
}
