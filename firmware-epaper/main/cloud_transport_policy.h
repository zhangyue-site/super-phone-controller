#pragma once
namespace controller {
// Wi-Fi always wins. The legacy callback must never run in production or on STA.
template<class Legacy>
inline bool cloud_transport_ready(bool wifi,bool maintenance_enabled,Legacy legacy){
 if(wifi)return true;
 return maintenance_enabled&&legacy();
}
}
