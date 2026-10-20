#include <cassert>
#include "touch_ui.h"
using namespace controller;
int main(){
 assert(touch_target(5,50,75)==TouchTarget::START);
 assert(touch_target(5,40,120)==TouchTarget::NONE);
 assert(touch_target(5,150,150)==TouchTarget::STOP);
 assert(touch_target(4,30,188)==TouchTarget::HOME);
 assert(touch_target(4,90,188)==TouchTarget::HOME);
 assert(touch_target(4,175,188)==TouchTarget::HOME);
 assert(touch_target(2,90,95)==TouchTarget::CONFIRM);
 assert(touch_target(5,250,75)==TouchTarget::NONE);
 assert(touch_target(3,80,90,4)==TouchTarget::START);
 TouchContact contact;
 assert(contact.update(-1)==TouchEdge::NONE);
 assert(contact.update(1)==TouchEdge::NONE); // unknown/multitouch cannot become new down
 assert(contact.update(0)==TouchEdge::UP);
 assert(contact.update(1)==TouchEdge::DOWN);
 assert(contact.update(-1)==TouchEdge::NONE);
 assert(contact.update(1)==TouchEdge::NONE);
 assert(contact.update(0)==TouchEdge::UP);
 TouchGesture g;
 assert(!g.begin(1,2,TouchTarget::START,0)); // screen still refreshing
 assert(!g.release(2,100));
 assert(g.begin(2,2,TouchTarget::START,200));
 assert(!g.release(3,300)); // disconnect/page change invalidates pending tap
 assert(g.begin(3,3,TouchTarget::CONFIRM,400));
 assert(!g.release(3,500)); // short touch cannot enable HID
 assert(g.begin(3,3,TouchTarget::CONFIRM,600));
 assert(g.release(3,2700));
 assert(g.begin(4,4,TouchTarget::START,2800));g.cancel();assert(!g.release(4,2900));
}
