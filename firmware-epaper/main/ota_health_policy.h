#pragma once
#include <stdint.h>
namespace controller {
inline bool ota_local_health(int64_t now,bool painted,int64_t input,int64_t screen,bool ble,unsigned memory){
 return now>=45000000 && painted && now-input<=2000000 && now-screen<=15000000 && ble && memory>=8192;
}
}
