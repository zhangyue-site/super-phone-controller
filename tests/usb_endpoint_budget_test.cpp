#include <cassert>
#include <cstdint>
#include "usb_endpoint_budget.h"
int main(){
 constexpr uint8_t raw[]={9,2,57,0,5,1,0,128,50,9,4,0,0,1,2,2,0,4,4,36,2,6,7,5,0x81,3,8,0,1,7,5,0x82,2,64,0,0,7,5,0x83,3,64,0,50,7,5,0x84,2,64,0,0,7,5,0x85,3,16,0,10};
 static_assert(controller::in_endpoint_count(raw,sizeof(raw))+1==6,"old composite exceeds S3 limit");
 constexpr auto fixed=controller::without_cdc_notification(raw);
 static_assert(fixed.size()==sizeof(raw)-7,"remove one descriptor only");
 static_assert(controller::in_endpoint_count(fixed.data(),fixed.size())+1==5,"fixed fits including EP0");
 assert(fixed[2]==sizeof(raw)-7 && fixed[3]==0);
 assert(fixed[fixed.size()-5]==0x81);assert(fixed[13]==0);assert(fixed[21]==4);
}
