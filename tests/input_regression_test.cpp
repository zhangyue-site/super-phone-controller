#include <cassert>
#include "touch_ui.h"
#include "gesture.h"
#include "input_policy.h"
#include "voice_transport_policy.h"
using namespace controller;
int main(){
 TouchGesture tap;assert(tap.begin(1,1,TouchTarget::PHONE_HOME,100));
 assert(tap.release(1,140)); // real 40ms contact seen on the board must be usable
 assert(touch_target(5,100,130,5)==TouchTarget::CONTROL);
 assert(touch_target(6,192,75,5)==TouchTarget::PHONE_HOME);
 assert(!is_navigation_gesture(Gesture::LongPress,TouchTarget::PHONE_HOME));
 assert(!is_navigation_gesture(Gesture::DoubleTap,TouchTarget::PHONE_HOME));
 assert(is_navigation_gesture(Gesture::SwipeUp,TouchTarget::PHONE_HOME));
 assert(is_navigation_gesture(Gesture::DoubleTap,TouchTarget::NONE));
 TouchGesture confirm;assert(confirm.begin(2,2,TouchTarget::CONFIRM,100));assert(!confirm.release(2,140));
 assert(confirm.begin(2,2,TouchTarget::CONFIRM,200));assert(confirm.release(2,2200));
 assert(!voice_ready(true,false,true,false,true));assert(voice_ready(true,false,true,true,true));
 assert(!voice_ready(false,false,true,true,true));assert(voice_ready(false,true,false,false,false));
 assert(voice_can_probe(true,false));assert(!voice_can_probe(false,false));
}
