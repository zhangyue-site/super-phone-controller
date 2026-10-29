#pragma once
#include <cstring>
namespace controller {
enum class UsbConsoleRoute { proof, stop, maintenance, denied };
inline UsbConsoleRoute usb_console_route(const char *line,bool maintenance){
 if(!line)return UsbConsoleRoute::denied;
 if(!std::strncmp(line,"PCUSB ",6))return UsbConsoleRoute::proof;
 if(!std::strcmp(line,"STOP"))return UsbConsoleRoute::stop;
 return maintenance?UsbConsoleRoute::maintenance:UsbConsoleRoute::denied;
}
inline bool usb_download_line_state(bool maintenance,bool switching,bool dtr,bool rts,bool& seen){
 if(!maintenance||switching){seen=false;return false;}
 if(!dtr&&rts){seen=true;return false;}
 bool download=seen&&dtr&&!rts;seen=false;return download;
}
template<class Proof,class Stop,class Maintenance,class Denied>
inline void usb_console_dispatch(char *line,bool maintenance,Proof proof,Stop stop,Maintenance command,Denied denied){
 switch(usb_console_route(line,maintenance)){
 case UsbConsoleRoute::proof:proof(line);break;
 case UsbConsoleRoute::stop:stop();break;
 case UsbConsoleRoute::maintenance:command(line);break;
 default:denied();break;
 }
}
}
