#pragma once
#include <cstdint>
class HoldToTalk {
public:
    enum Action { None, Start, Finish };
    Action update(bool held, uint32_t now) {
        if (!held) {
            bool finish = active_; down_=active_=latched_=false;
            return finish ? Finish : None;
        }
        if (!down_) { down_=true; began_=now; }
        if (!active_ && !latched_ && uint32_t(now-began_)>=800) {
            active_=latched_=true; return Start;
        }
        if (active_ && uint32_t(now-began_)>=12800) { active_=false; return Finish; }
        return None;
    }
    void release() { down_=active_=latched_=false; }
private:
    bool down_=false,active_=false,latched_=false;
    uint32_t began_=0;
};
