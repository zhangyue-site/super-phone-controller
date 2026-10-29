#include "cloud_transport_policy.h"
#include "adb_local.h"
#include <cassert>
int main(){
 unsigned calls=0;auto legacy=[&](){++calls;return true;};
 assert(controller::cloud_transport_ready(true,false,legacy));assert(calls==0);
 assert(controller::cloud_transport_ready(true,true,legacy));assert(calls==0);
 assert(!controller::cloud_transport_ready(false,false,legacy));assert(calls==0);
 assert(controller::cloud_transport_ready(false,true,legacy));assert(calls==1);
 controller_adb_init();assert(!controller_adb_activate(0));assert(!controller_adb_network_available());
 assert(controller_adb_ticket()==0&&controller_adb_stage()==0&&controller_adb_error()==0);
 controller::AdbCommand command{};char output[4]={};const char *error=nullptr;
 assert(!controller_adb_execute(command,nullptr,output,sizeof(output),0,&error));assert(error);
 controller_adb_cancel();assert(controller_adb_stage()==0);
}
