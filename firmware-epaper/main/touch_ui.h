#pragma once
#include <cstdint>
namespace controller {
inline int next_page(int current,int home){return (current+1)%(home+7);}
inline int previous_page(int current,int home){return (current+home+6)%(home+7);}
enum class TouchTarget {NONE,START,QUOTA,CONTROL,HOME,STOP,CONFIRM,UP,DOWN,LEFT,RIGHT,CLICK,PHONE_HOME,PHONE_BACK,UPDATE,VOLUME_DOWN,VOLUME_UP,MUTE,SOUND_TEST,SOUND_SETTINGS};
inline TouchTarget touch_target(int page,int x,int y,int home=5){
 if(x<8||x>=192||y<0||y>=188)return TouchTarget::NONE;
 if(page==home&&x>=140&&y<28)return TouchTarget::SOUND_SETTINGS;
 if(y>=162)return x<100?TouchTarget::HOME:TouchTarget::STOP;
 if(page==home+6){
  if(y>=54&&y<100)return x<100?TouchTarget::VOLUME_DOWN:TouchTarget::VOLUME_UP;
  if(y>=108&&y<154)return x<100?TouchTarget::MUTE:TouchTarget::SOUND_TEST;
  return TouchTarget::NONE;
 }
 bool top=y>=45&&y<100,bottom=y>=105&&y<155;
 if(page==home+5)return top?TouchTarget::UPDATE:bottom?TouchTarget::HOME:TouchTarget::NONE;
 if(page==2)return y>=65&&y<125?TouchTarget::CONFIRM:TouchTarget::NONE;
 if(page==home)return top?TouchTarget::START:bottom?TouchTarget::CONTROL:TouchTarget::NONE;
 if(page==home+1)return top?TouchTarget::PHONE_HOME:bottom?TouchTarget::PHONE_BACK:TouchTarget::NONE;
 if(page==home+2)return top?TouchTarget::LEFT:bottom?TouchTarget::RIGHT:TouchTarget::NONE;
 if(page==home+3)return top?TouchTarget::UP:bottom?TouchTarget::DOWN:TouchTarget::NONE;
 if(page==home+4)return top?TouchTarget::CLICK:bottom?TouchTarget::STOP:TouchTarget::NONE;
 if(page==home-1&&y>=45&&y<100)return TouchTarget::START;
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
