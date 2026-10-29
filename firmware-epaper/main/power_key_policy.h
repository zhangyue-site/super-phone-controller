#pragma once
#include <stdint.h>
namespace controller {
enum class PowerEvent { NONE, ARMED, OFF, RESTART };
// GPIO18 is active low. A stable release after boot is mandatory, including
// after a software restart at 30 s. Debounce is owned here, independently of UI.
struct PowerKeyHold {
 bool ready=false, raw=false, down=false, held=false, armed=false, fired=false;
 int64_t changed=0, began=0; bool initialized=false;
 PowerEvent update(bool pressed,int64_t now){
  if(!initialized){initialized=true;raw=pressed;changed=now;return PowerEvent::NONE;}
  if(pressed!=raw){raw=pressed;changed=now;}
  if(now-changed<40)return PowerEvent::NONE;
  down=raw;
  if(!ready){if(!down)ready=true;return PowerEvent::NONE;}
  if(down&&!held){held=true;armed=false;fired=false;began=now;}
  if(down&&held&&!fired){
   if(now-began>=30000){fired=true;return PowerEvent::RESTART;}
   if(now-began>=5000&&!armed){armed=true;return PowerEvent::ARMED;}
  }
  if(!down&&held){held=false;if(!fired&&now-began>=5000){armed=false;return PowerEvent::OFF;}armed=false;}
  return PowerEvent::NONE;
 }
};
enum class PowerRequest { NONE, OFF, RESTART };
enum class PowerDrainAction { NONE, WAIT, WAIT_COMMIT, ACQUIRE, FAILED };
struct PowerDrain {
 PowerRequest pending=PowerRequest::NONE;int64_t since=0;
 void request(PowerRequest value,int64_t now){if(pending==PowerRequest::NONE){pending=value;since=now;}}
 // ACQUIRE means attempt CAS(IDLE -> POWER), never permission to act on a snapshot.
 PowerDrainAction update(bool idle,bool commit,int64_t now){
  if(pending==PowerRequest::NONE)return PowerDrainAction::NONE;
  if(now-since>=20000){pending=PowerRequest::NONE;return PowerDrainAction::FAILED;}
  if(idle)return PowerDrainAction::ACQUIRE;
  return commit?PowerDrainAction::WAIT_COMMIT:PowerDrainAction::WAIT;
 }
};
}
