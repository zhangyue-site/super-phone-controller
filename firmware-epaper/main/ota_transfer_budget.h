#pragma once
#include <stdint.h>
namespace controller {
// A slow but progressing link may use its size-based budget; no progress is
// independently limited to 15s, matching the existing HTTP read timeout.
inline int64_t ota_transfer_budget_us(uint32_t bytes){
 int64_t seconds=(int64_t(bytes)+2047)/2048+120;
 if(seconds<600)seconds=600;
 if(seconds>1200)seconds=1200;
 return seconds*1000000;
}
struct OtaTransferBudget {
 int64_t started,last_receive,budget;
 OtaTransferBudget(uint32_t bytes,int64_t now):started(now),last_receive(now),budget(ota_transfer_budget_us(bytes)){}
 bool total_expired(int64_t now)const{return now-started>=budget;}
 bool idle_expired(int64_t now)const{return now-last_receive>=15000000;}
 bool live(int64_t now)const{return !total_expired(now)&&!idle_expired(now);}
 void received(int64_t now){last_receive=now;}
};
}
