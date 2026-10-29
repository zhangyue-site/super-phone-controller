#pragma once
#include <stdint.h>
#include <stddef.h>
#include "keyboard_policy.h"
namespace controller {
struct BleLocalPacket {uint8_t op;uint32_t sequence;uint16_t x,y,x2,y2,ms;};
inline uint16_t ble_u16(const uint8_t *p){return uint16_t(p[0])|(uint16_t(p[1])<<8);}
inline bool ble_local_parse(const uint8_t *p,size_t n,BleLocalPacket& c){
 if(n!=48||p[0]!=1||p[1]<1||p[1]>14)return false;
 c={p[1],uint32_t(p[2])|(uint32_t(p[3])<<8)|(uint32_t(p[4])<<16)|(uint32_t(p[5])<<24),ble_u16(p+6),ble_u16(p+8),ble_u16(p+10),ble_u16(p+12),ble_u16(p+14)};
 if(!c.sequence)return false;
 if(c.op==3)return c.x<=32767&&c.y<=32767&&!c.x2&&!c.y2&&!c.ms;
 if(c.op==4)return c.x<=32767&&c.y<=32767&&c.x2<=32767&&c.y2<=32767&&c.ms>=100&&c.ms<=1200;
 if(c.op==13)return c.x<=255&&keyboard_usage(c.y)&&!c.x2&&!c.y2&&!c.ms;
 if(c.op==14){uint16_t words[]={c.y,c.x2,c.y2,c.ms};return ascii_packet(c.x,words);}
 if(c.op==8)return c.x>=4&&c.x<=231&&!c.y&&!c.x2&&!c.y2&&!c.ms;
 return !c.x&&!c.y&&!c.x2&&!c.y2&&!c.ms;
}
inline bool ble_local_fresh(uint32_t incoming,uint32_t previous){return incoming>previous;}
}
