#include "product_display_policy.h"
#include "touch_ui.h"
#include "product_screens.h"
#include <cassert>
int main(){using namespace controller;
 for(unsigned bits=0;bits<128;++bits){bool usb=bits&1,hid=bits&2,network=bits&4,relay=bits&8,stopped=bits&16,failed=bits&32,seen=bits&64;
  int state=product_home_state(usb,hid,network,relay,stopped,failed,seen);
  assert(state>=0&&state<=7);
  if(stopped)assert(state==PRODUCT_STOPPED);
  else if(failed)assert(state==PRODUCT_FAILED);
  else if(!usb)assert(state==(seen?PRODUCT_DISCONNECTED:PRODUCT_WAIT_USB));
  else if(!hid)assert(state==PRODUCT_PERMISSION); // BLE/IP cannot manufacture permission.
  else if(relay)assert(state==PRODUCT_RELAY);
  else if(!network)assert(state==PRODUCT_WAIT_NETWORK);
  else assert(state==PRODUCT_ALLOWED); // Local permission only, never full phone readiness.
 }
 assert(product_home_state(false,false,true,true,false,false,false)==PRODUCT_WAIT_USB);
 assert(product_home_state(true,false,true,true,false,false,true)==PRODUCT_PERMISSION);
 for(unsigned p=0;p<=120;++p){unsigned shown=product_progress(p);assert(shown<=100&&shown%10==0);assert(shown<=p);if(p<100)assert(p-shown<10);}
 for(int page=0;page<12;++page){
  for(int y=162;y<188;++y)for(int x=100;x<200;++x)assert(touch_target(page,x,y)==TouchTarget::STOP);
  assert(touch_target(page,199,188)==TouchTarget::NONE);
 }
 for(int y=65;y<125;++y)for(int x=0;x<200;++x)assert(touch_target(2,x,y)==TouchTarget::CONFIRM);
 assert(touch_target(2,10,64)==TouchTarget::NONE);assert(touch_target(2,10,125)==TouchTarget::NONE);
 assert(touch_target(5,50,44)==TouchTarget::SOUND_SETTINGS);
 assert(touch_target(5,50,45)==TouchTarget::START);assert(touch_target(5,50,100)==TouchTarget::NONE);
 assert(touch_target(5,50,105)==TouchTarget::CONTROL);assert(touch_target(5,50,155)==TouchTarget::NONE);
 static_assert(sizeof(product_home[0])==5000&&sizeof(product_mode[0])==5000&&sizeof(product_power[0])==5000,"200x200 1bpp");
 static_assert(sizeof(product_footer[0])==650,"26 rows shared footer");
 TouchGesture g;assert(!g.begin(2,1,TouchTarget::CONFIRM,0));assert(g.begin(2,2,TouchTarget::CONFIRM,0));assert(!g.release(2,1999));assert(g.begin(2,2,TouchTarget::CONFIRM,0));assert(!g.release(3,2001));assert(g.begin(2,2,TouchTarget::CONFIRM,0));assert(g.release(2,2001));
}
