#include "ota_resume_policy.h"
#include "ota_transfer_budget.h"
#include "ota_guard.h"
#include <cassert>
#include <vector>
#include <cstdint>
using namespace controller;
int main(){
 assert(ota_resume_response(206,"bytes 163840-2170543/2170544",2006704,163840,2170544));
 assert(ota_resume_response(206,"bytes 0-2170543/2170544",2170544,0,2170544));
 for(int status:{200,401,403,416,500})assert(!ota_resume_response(status,"bytes 163840-2170543/2170544",2006704,163840,2170544));
 for(const char *range:{"bytes 163839-2170543/2170544","bytes 163840-2170542/2170544","bytes 163840-2170543/2170545","bytes */2170544","bytes 163840-2170543/*","bytes 163840-2170543/2170544 extra","bytes 18446744073709551616-2170543/2170544","bytes -1-2170543/2170544","bytes 163840-2170543/2170544,bytes 1-2/3","bytes 163840-2170543/"})assert(!ota_resume_response(206,range,2006704,163840,2170544));
 assert(!ota_resume_response(206,"bytes 163840-2170543/2170544",2170544,163840,2170544));
 assert(!ota_resume_response(206,nullptr,1,0,1));
 OtaResumePolicy retry;assert(retry.take_attempt(false,false));assert(retry.delay_ms()==250);assert(retry.take_attempt(false,false));assert(retry.take_attempt(false,false));assert(!retry.take_attempt(false,false));assert(retry.attempts==3);
 OtaResumePolicy stopped;assert(!stopped.take_attempt(true,false));assert(stopped.attempts==0);assert(!stopped.take_attempt(false,true));assert(stopped.attempts==0);
 // A new validated range starts a waiting window, not a fake body timestamp.
 assert(ota_receive_window_expired(30000000,0,0));assert(!ota_receive_window_expired(30000000,0,29000000));assert(ota_receive_window_expired(44000000,0,29000000));
 // Simulated link break after committed prefix, then exact range appends once.
 std::vector<unsigned char> image(20000),flash;for(unsigned i=0;i<image.size();i++)image[i]=(i*37+11)%251;
 flash.insert(flash.end(),image.begin(),image.begin()+8192);uint32_t offset=flash.size();
 assert(ota_guard_acquire(OTA_WIFI));assert(!ota_guard_acquire(OTA_BLE));
 assert(!ota_resume_response(200,"bytes 8192-19999/20000",11808,offset,20000));assert(flash.size()==8192);
 assert(ota_resume_response(206,"bytes 8192-19999/20000",11808,offset,20000));flash.insert(flash.end(),image.begin()+offset,image.end());assert(flash==image);assert(ota_guard_commit(OTA_WIFI));ota_guard_release(OTA_WIFI);
 // STOP while reconnecting forbids both a fresh retry and commit, preserving prefix.
 assert(ota_guard_acquire(OTA_WIFI));ota_guard_cancel(OTA_WIFI);OtaResumePolicy cancelled;assert(!cancelled.take_attempt(ota_guard_cancelled(OTA_WIFI),false));assert(!ota_guard_commit(OTA_WIFI));ota_guard_release(OTA_WIFI);
}
