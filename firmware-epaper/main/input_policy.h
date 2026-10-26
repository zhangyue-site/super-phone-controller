#pragma once
#include "gesture.h"
#include "touch_ui.h"
namespace controller {
inline bool is_navigation_gesture(Gesture value,TouchTarget target){
 return value==Gesture::SwipeUp || value==Gesture::SwipeDown ||
  (value==Gesture::DoubleTap && target==TouchTarget::NONE);
}
}
