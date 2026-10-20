#pragma once
#include "hold_to_talk.h"
class TaskButton {
public:
    enum Action { None, Run, VoiceStart, VoiceFinish, Cancel };
    Action update(bool pressed,bool busy,uint32_t now){
        Action result=None;
        if(pressed && !down_){voice_=false;suppressed_=busy;if(busy)result=Cancel;}
        auto hold=hold_.update(pressed && !suppressed_,now);
        if(hold==HoldToTalk::Start){voice_=true;result=VoiceStart;}
        if(hold==HoldToTalk::Finish)result=VoiceFinish;
        if(!pressed && down_ && !voice_ && !suppressed_)result=Run;
        down_=pressed;return result;
    }
    void reset(){down_=voice_=suppressed_=false;hold_.release();}
private:
    bool down_=false,voice_=false,suppressed_=false;
    HoldToTalk hold_;
};
