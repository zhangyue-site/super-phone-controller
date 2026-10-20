#pragma once
#include <cstdint>
namespace controller {
enum class TouchTarget {NONE,START,QUOTA,CONTROL,HOME,STOP,CONFIRM};
inline TouchTarget touch_target(int page,int x,int y,int home=5){
 if(x<0||x>=200||y<0||y>=200)return TouchTarget::NONE;
 if(page==home){
  if(x>=8&&x<192&&y>=54&&y<100)return TouchTarget::START;
  if(y>=110&&y<145){if(x>=8&&x<95)return TouchTarget::QUOTA;if(x>=105&&x<192)return TouchTarget::CONTROL;}
  if(x>=8&&x<192&&y>=151&&y<177)return TouchTarget::STOP;
 }else{
  if(y>=178)return x<60?TouchTarget::HOME:x<140?TouchTarget::START:TouchTarget::STOP;
  if(page==2&&x>=8&&x<192&&y>=65&&y<125)return TouchTarget::CONFIRM;
 }
 return TouchTarget::NONE;
}
enum class TouchEdge {NONE,DOWN,UP};
struct TouchContact {
 bool held=false;
 TouchEdge update(int contact){
  if(contact<0){held=true;return TouchEdge::NONE;}
  if(contact==0){bool was=held;held=false;return was?TouchEdge::UP:TouchEdge::NONE;}
  if(held)return TouchEdge::NONE;
  held=true;return TouchEdge::DOWN;
 }
};
struct TouchGesture {
 bool active=false;unsigned epoch=0;TouchTarget target=TouchTarget::NONE;int64_t began=0;
 bool begin(unsigned current,unsigned painted,TouchTarget value,int64_t now){
  cancel();if(current!=painted||value==TouchTarget::NONE)return false;
  active=true;epoch=current;target=value;began=now;return true;
 }
 bool release(unsigned current,int64_t now){
  bool ok=active&&current==epoch&&now-began>=50&&now-began<10000&&
   (target!=TouchTarget::CONFIRM||now-began>=2000);
  active=false;return ok;
 }
 void cancel(){active=false;target=TouchTarget::NONE;}
};
}
