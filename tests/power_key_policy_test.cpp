#include <cassert>
#include <cstdio>
#include "power_key_policy.h"
#include "button_gesture.h"
#include "ota_guard.h"
using namespace controller;
static PowerKeyHold ready(){PowerKeyHold k;k.update(false,0);k.update(false,40);assert(k.ready);return k;}
static void press(PowerKeyHold& k,int64_t t){k.update(true,t);k.update(true,t+40);}
int main(){
 {auto k=ready();press(k,100);assert(k.update(true,5139)==PowerEvent::NONE);assert(k.update(true,5140)==PowerEvent::ARMED);k.update(false,6000);assert(k.update(false,6040)==PowerEvent::OFF);assert(k.update(false,7000)==PowerEvent::NONE);}
 {auto k=ready();press(k,100);assert(k.update(true,5140)==PowerEvent::ARMED);assert(k.update(true,30140)==PowerEvent::RESTART);assert(k.update(true,99999)==PowerEvent::NONE);k.update(false,100000);assert(k.update(false,100040)==PowerEvent::NONE);}
 {PowerKeyHold k;assert(k.update(true,0)==PowerEvent::NONE);assert(k.update(true,40000)==PowerEvent::NONE);k.update(false,40001);k.update(true,40020);k.update(true,90000);assert(!k.ready);k.update(false,90001);k.update(false,90041);assert(k.ready);press(k,90100);assert(k.update(true,95140)==PowerEvent::ARMED);}
 {auto k=ready();k.update(true,100);k.update(false,120);k.update(false,160);assert(!k.held);press(k,200);k.update(false,300);k.update(true,320);assert(k.update(true,5240)==PowerEvent::ARMED);}
 {ControlButton b;assert(b.update(true,100)==ControlEvent::NONE);assert(b.update(true,700)==ControlEvent::STOP);assert(b.update(false,6000)==ControlEvent::NONE);assert(b.update(false,6400)==ControlEvent::NONE);}
 {PowerDrain d;d.request(PowerRequest::OFF,100);assert(d.update(false,false,200)==PowerDrainAction::WAIT);assert(d.update(false,true,500)==PowerDrainAction::WAIT_COMMIT);assert(d.update(true,false,600)==PowerDrainAction::ACQUIRE);assert(d.pending==PowerRequest::OFF);}
 {PowerDrain d;d.request(PowerRequest::RESTART,100);assert(d.update(false,true,20099)==PowerDrainAction::WAIT_COMMIT);assert(d.update(false,true,20100)==PowerDrainAction::FAILED);assert(d.pending==PowerRequest::NONE);}
 assert(ota_guard_get_phase()==OTA_GUARD_IDLE);assert(ota_guard_acquire(OTA_BLE));ota_guard_cancel(OTA_BLE);assert(ota_guard_cancelled(OTA_BLE));assert(!ota_guard_commit(OTA_BLE));ota_guard_release(OTA_BLE);
 assert(ota_guard_acquire(OTA_WIFI));assert(ota_guard_commit(OTA_WIFI));ota_guard_cancel(OTA_WIFI);assert(ota_guard_get_phase()==OTA_GUARD_COMMIT);assert(!ota_guard_acquire(OTA_POWER));ota_guard_release(OTA_WIFI);
 // A writer wins between snapshot and reservation: power must retry, never act.
 assert(ota_guard_get_phase()==OTA_GUARD_IDLE);assert(ota_guard_acquire(OTA_BLE));assert(!ota_guard_acquire(OTA_POWER));ota_guard_release(OTA_BLE);
 assert(ota_guard_acquire(OTA_POWER));assert(ota_guard_get_phase()==OTA_GUARD_POWER);assert(!ota_guard_acquire(OTA_WIFI));assert(!ota_guard_acquire(OTA_BLE));ota_guard_release(OTA_POWER);
 puts("power key + drain + guard: PASS");
}
