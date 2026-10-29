#pragma once
#include <stdint.h>

namespace controller {
// Deliberately no NVS/RTC state: each startup must ask again.
constexpr bool hid_on_boot() { return false; }
constexpr bool wifi_on_boot() { return false; }
constexpr bool can_confirm(int64_t visible_at, int64_t press_at, int64_t now,
                           bool same_screen = true) {
    return same_screen && visible_at > 0 && press_at >= visible_at &&
           now >= press_at && now - press_at >= 2000 &&
           now - visible_at < 15000;
}
struct ConfirmKeyResult {bool consume=false,confirm=false;int64_t began=0;};
struct LocalConfirmKey {
 bool capturing=false,fired=false,armed=false;int64_t began=0;
 ConfirmKeyResult update(bool pressed,bool on_page,bool eligible,int64_t visible,int64_t now){
  if(!pressed){bool consumed=capturing;capturing=fired=armed=false;began=0;return {consumed,false,0};}
  if(!capturing){if(!on_page)return {};capturing=true;began=now;armed=eligible;}
  if(!on_page||!eligible)armed=false;
  if(armed&&!fired&&can_confirm(visible,began,now)){fired=true;return {true,true,began};}
  return {true,false,began};
 }
};
}
