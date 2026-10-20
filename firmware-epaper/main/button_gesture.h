#pragma once
#include <cstdint>
namespace controller {
enum class ButtonEvent {NONE,NEXT,HOME,VOICE_DOWN,VOICE_UP};
struct ButtonGesture {
 bool down=false,voicing=false,pending=false,second=false;
 int64_t pressed=0,released=0;
 ButtonEvent update(bool value,int64_t now){
  if(value&&!down){down=true;pressed=now;voicing=false;second=pending&&now-released<=320;if(second)pending=false;}
  if(down&&value&&!voicing&&now-pressed>=600){voicing=true;pending=false;return ButtonEvent::VOICE_DOWN;}
  if(down&&!value){
   down=false;
   if(voicing){voicing=false;return ButtonEvent::VOICE_UP;}
   if(now-pressed<40)return ButtonEvent::NONE;
   if(second){second=false;pending=false;return ButtonEvent::HOME;}
   released=now;pending=true;
  }
  if(!down&&pending&&now-released>320){pending=false;return ButtonEvent::NEXT;}
  return ButtonEvent::NONE;
 }
};
}
