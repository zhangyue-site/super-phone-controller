#include "device_auth.h"
#include "device_config.h"
#include "psa/crypto.h"
#include <string.h>
bool controller_device_sign(const char *domain,const uint8_t nonce[32],uint8_t proof[32]){
 uint8_t message[256];size_t n=strlen(domain);if(n+32>sizeof(message))return false;
 memcpy(message,domain,n);memcpy(message+n,nonce,32);memset(proof,0,32);
 psa_key_attributes_t attributes=PSA_KEY_ATTRIBUTES_INIT;psa_key_id_t key=0;
 psa_set_key_usage_flags(&attributes,PSA_KEY_USAGE_SIGN_MESSAGE);
 psa_set_key_algorithm(&attributes,PSA_ALG_HMAC(PSA_ALG_SHA_256));psa_set_key_type(&attributes,PSA_KEY_TYPE_HMAC);
 psa_status_t result=psa_import_key(&attributes,(const uint8_t*)DISPLAY_TOKEN,strlen(DISPLAY_TOKEN),&key);
 psa_reset_key_attributes(&attributes);size_t length=0;
 if(result==PSA_SUCCESS){result=psa_mac_compute(key,PSA_ALG_HMAC(PSA_ALG_SHA_256),message,n+32,proof,32,&length);psa_destroy_key(key);}
 memset(message,0,sizeof(message));return result==PSA_SUCCESS && length==32;
}
