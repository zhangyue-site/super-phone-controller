#pragma once
namespace controller {
// Display-only facts. Network/IP presence is deliberately never called cloud-ready.
enum ProductHome { PRODUCT_WAIT_USB,PRODUCT_PERMISSION,PRODUCT_ALLOWED,PRODUCT_RELAY,PRODUCT_STOPPED,PRODUCT_DISCONNECTED,PRODUCT_FAILED,PRODUCT_WAIT_NETWORK };
inline int product_home_state(bool usb,bool hid,bool network,bool relay,bool stopped,bool failed,bool seen_usb){
 if(stopped)return PRODUCT_STOPPED;
 if(failed)return PRODUCT_FAILED;
 if(!usb)return seen_usb?PRODUCT_DISCONNECTED:PRODUCT_WAIT_USB;
 if(!hid)return PRODUCT_PERMISSION;
 if(relay)return PRODUCT_RELAY;
 if(!network)return PRODUCT_WAIT_NETWORK;
 return PRODUCT_ALLOWED;
}
inline int product_network_state(bool usb,bool wifi,bool relay){
 if(wifi)return 1;
 if(relay)return 2;
 return usb?3:0;
}
inline unsigned product_progress(unsigned progress){return (progress>100?100:progress)/10*10;}
}
