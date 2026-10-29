#include <cassert>
#include <initializer_list>
#include "../firmware-epaper/main/relay_display_policy.h"
int main() {
 using namespace controller;
 assert(relay_display(true,true,false,false,false,false)==RELAY_CONNECTED);
 assert(relay_display(true,true,true,false,false,false)==RELAY_CONTROLLING);
 assert(relay_display(true,false,false,false,false,false)==RELAY_DIRECT_OFFLINE);
 assert(relay_display(true,false,false,true,false,false)==RELAY_LEGACY);
 for(bool connected:{false,true}) {
  assert(relay_display(false,connected,true,false,false,false)==RELAY_LEGACY);
  assert(relay_display(true,connected,true,false,true,false)==RELAY_LEGACY);
  assert(relay_display(true,connected,true,false,false,true)==RELAY_LEGACY);
 }
}
