#pragma once
#include <cstdint>
namespace controller {
enum class TouchTarget {NONE,START,QUOTA,CONTROL,HOME,STOP,CONFIRM};
inline TouchTarget touch_target(int page,int x,int y,int home=5){
 if(x<0||x>=200||y<0||y>=200)return TouchTarget::NONE;
 if(page==home){
  if(x>=8&&x<192&&y>=52&&y<=118)return TouchTarget::START;
  if(x>=8&&x<192&&y>=130&&y<=175)return TouchTarget::STOP;
 }else{
  if(y>=178)return TouchTarget::HOME;
  if(page==2&&x>=8&&x<192&&y>=65&&y<125)return TouchTarget::CONFIRM;
  if(page==home-1&&x>=8&&x<192&&y>=52&&y<=118)return TouchTarget::START;
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
