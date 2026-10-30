#pragma once
#include <stdint.h>
namespace controller {
constexpr bool consent_short_tap(int64_t visible,int64_t began,int64_t now,bool same){
 return same&&visible>0&&began>=visible&&now>=began&&now-began>=20&&now-began<=700&&now-visible<15000;
}
struct ConsentExitKeyGate {
 bool blocked=false;
 void on_consent_page(){blocked=true;}
 bool admit(bool pressed){if(!blocked)return true;if(!pressed)blocked=false;return false;}
};
template<class Advance,class Apply>
inline void consent_tap_transition(int step,Advance advance,Apply apply){
 if(step==0)advance();else if(step==1)apply();
}
struct ConsentTapResult {bool confirm=false;int64_t began=0;};
// One input (touch or BOOT). A rendered new epoch must observe release before a new down.
struct ConsentTapInput {
 unsigned epoch=0;bool released=false,pressed=true,active=false;int64_t began=0;
 ConsentTapResult update(int contact,bool inside,bool ready,unsigned current,int64_t visible,int64_t now){
  if(epoch!=current){epoch=current;released=false;pressed=true;active=false;began=0;}
  if(contact!=0&&contact!=1){released=false;pressed=true;active=false;return {};}
  if(contact==0){
   bool ok=active&&ready&&consent_short_tap(visible,began,now,true);
   int64_t start=began;released=true;pressed=false;active=false;return {ok,start};
  }
  if(!pressed){
   pressed=true;active=released&&ready&&inside;released=false;began=now;
  }
  if(active&&(!ready||!inside||now-began>700))active=false;
  return {};
 }
};
}
