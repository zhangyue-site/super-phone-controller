#include "tap_consent.h"
#include <cassert>
using controller::ConsentTapInput;
int main(){
 int step=0,grants=0;unsigned flow_epoch=1;ConsentTapInput flow;
 auto event=[&](int contact,bool ready,long visible,long time){auto tap=flow.update(contact,true,ready,flow_epoch,visible,time);if(tap.confirm)controller::consent_tap_transition(step,[&](){step=1;++flow_epoch;},[&](){++grants;});};
 event(0,true,100,110);event(1,true,100,200);event(0,true,100,300);assert(step==1&&grants==0);
 event(1,false,0,320);event(1,true,400,500);event(0,true,400,600);assert(grants==0); // No release/new-down after new frame.
 event(1,true,400,700);event(0,true,400,800);assert(grants==1);
 controller::consent_tap_transition(9,[](){assert(false);},[](){assert(false);});
 ConsentTapInput gate;
 auto u=[&](int c,bool inside,bool ready,unsigned e,long v,long t){return gate.update(c,inside,ready,e,v,t);};
 assert(!u(1,true,true,1,100,110).confirm); // Held on entering page; no prior release.
 assert(!u(1,true,true,1,100,2500).confirm);assert(!u(0,false,true,1,100,2600).confirm);
 assert(!u(1,true,true,1,100,2700).confirm);assert(u(0,false,true,1,100,2800).confirm); // First short tap.
 assert(!u(1,true,true,2,2900,3000).confirm); // New epoch needs new release.
 assert(!u(0,false,true,2,2900,3100).confirm);
 assert(!u(1,true,false,2,2900,3200).confirm);assert(!u(1,true,true,2,2900,3300).confirm);assert(!u(0,false,true,2,2900,3400).confirm); // During painting then held.
 assert(!u(1,true,true,2,2900,3500).confirm);assert(u(0,false,true,2,2900,3600).confirm);
 assert(!u(1,true,true,3,3700,3800).confirm);assert(!u(0,false,true,3,3700,3810).confirm);
 assert(!u(1,true,true,3,3700,3900).confirm);assert(!u(0,false,true,3,3700,3910).confirm); // Bounce below20ms.
 assert(!u(1,true,true,3,3700,4000).confirm);assert(!u(-1,true,true,3,3700,4020).confirm);assert(!u(1,true,true,3,3700,4100).confirm);assert(!u(0,false,true,3,3700,4200).confirm); // Bad I2C/contact cancels.
 assert(!u(1,true,true,3,3700,4300).confirm);assert(!u(1,false,true,3,3700,4350).confirm);assert(!u(0,false,true,3,3700,4400).confirm); // Move outside.
 assert(!u(1,true,true,3,3700,4500).confirm);assert(!u(1,true,true,3,3700,6500).confirm);assert(!u(0,false,true,3,3700,6600).confirm); // Old two-second hold never grants.
 assert(!u(1,true,true,3,3700,6700).confirm);assert(!u(0,false,true,4,6800,6900).confirm); // STOP/back/new screen invalidates captured down.
 assert(!u(1,true,true,4,6800,7000).confirm);assert(!u(0,false,true,4,7050,7100).confirm); // New visible paint after down.
 assert(!controller::consent_short_tap(100,200,300,false));assert(!controller::consent_short_tap(100,200,15100,true));
 // HOME is its own independent region and cannot act as confirm.
 ConsentTapInput home,confirm;
 home.update(0,false,true,8,100,110);confirm.update(0,false,true,8,100,110);
 home.update(1,true,true,8,100,200);confirm.update(1,false,true,8,100,200);
 assert(home.update(0,false,true,8,100,300).confirm);assert(!confirm.update(0,false,true,8,100,300).confirm);
 controller::ConsentExitKeyGate exit;exit.on_consent_page();
 for(int i=0;i<1000;++i)assert(!exit.admit(true)); // Continuous hold after exit cannot become next-page/voice.
 assert(!exit.admit(false));assert(exit.admit(true));
 // Physical BOOT uses the exact same gate and cannot carry a press between stages.
 ConsentTapInput key;assert(!key.update(0,true,true,10,100,110).confirm);assert(!key.update(1,true,true,10,100,200).confirm);assert(key.update(0,true,true,10,100,300).confirm);
 assert(!key.update(1,true,true,11,400,500).confirm);assert(!key.update(1,true,true,11,400,600).confirm);assert(!key.update(0,true,true,11,400,700).confirm);assert(!key.update(1,true,true,11,400,800).confirm);assert(key.update(0,true,true,11,400,900).confirm);
}
