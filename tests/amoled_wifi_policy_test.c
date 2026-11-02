#include "wifi_policy.h"
#include <assert.h>
#include <string.h>
int main(void){
 assert(pc_wifi_config_valid("test-network","test-password","https://controller.test"));
 const char *bad[]={"http://controller.test","https://user:pass@controller.test","https://controller.test/a?x=1","https://controller.test/#a","https://controller.test/","https://controller.test\\x","https://controller.test/%2f","https://controller.test\n","https://[::1]","https://controller.test:99999"};
 for(unsigned i=0;i<sizeof(bad)/sizeof(*bad);i++)assert(!pc_wifi_config_valid("test","test-password",bad[i]));
 assert(!pc_wifi_config_valid("","test-password","https://controller.test"));
 assert(!pc_wifi_config_valid("test","short","https://controller.test"));
 assert(pc_wifi_maintenance_allowed(true,false,false,false));
 assert(!pc_wifi_maintenance_allowed(false,false,false,false));
 assert(!pc_wifi_maintenance_allowed(true,true,false,false));
 assert(!pc_wifi_maintenance_allowed(true,false,true,false));
 assert(!pc_wifi_maintenance_allowed(true,false,false,true));
 uint32_t n;char sha[65],version[32];
 const char *valid="PCOTA1\n4096\n0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n0.3.1-amoled\n";
 assert(pc_wifi_manifest(valid,strlen(valid),&n,sha,version));assert(n==4096);
 assert(!pc_wifi_manifest(valid,strlen(valid)-1,&n,sha,version));
 char trailing[200];strcpy(trailing,valid);strcat(trailing,"unexpected");
 assert(!pc_wifi_manifest(trailing,strlen(trailing),&n,sha,version));
 assert(!pc_wifi_manifest("PCOTA1\n99999999999999999999\n0\nv\n",37,&n,sha,version));
 return 0;
}

