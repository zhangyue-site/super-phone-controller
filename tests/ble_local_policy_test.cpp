#include "ble_local_policy.h"
#include <cassert>
#include <cstring>
#include <random>
int main(){
 uint8_t p[64]={1,1,1};controller::BleLocalPacket c{};
 for(size_t n=0;n<=64;++n)assert(controller::ble_local_parse(p,n,c)==(n==48));
 p[0]=0;assert(!controller::ble_local_parse(p,48,c));p[0]=1;
 p[2]=0;assert(!controller::ble_local_parse(p,48,c));p[2]=1;
 for(unsigned op=1;op<=7;++op){memset(p,0,sizeof(p));p[0]=1;p[1]=op;p[2]=1;if(op==4){p[14]=100;}assert(controller::ble_local_parse(p,48,c));}
 for(unsigned op: {0u,8u,255u}){p[1]=op;assert(!controller::ble_local_parse(p,48,c));}
 memset(p,0,sizeof(p));p[0]=1;p[1]=3;p[2]=1;p[6]=255;p[7]=127;assert(controller::ble_local_parse(p,48,c));p[7]=128;assert(!controller::ble_local_parse(p,48,c));p[7]=0;p[10]=1;assert(!controller::ble_local_parse(p,48,c));
 memset(p,0,sizeof(p));p[0]=1;p[1]=4;p[2]=1;
 for(unsigned ms: {0u,99u,100u,1200u,1201u,65535u}){p[14]=ms&255;p[15]=ms>>8;assert(controller::ble_local_parse(p,48,c)==(ms>=100&&ms<=1200));}
 assert(controller::ble_local_fresh(1,0));assert(!controller::ble_local_fresh(1,1));assert(!controller::ble_local_fresh(1,2));assert(!controller::ble_local_fresh(0,0xffffffff));
 std::mt19937 rng(71025);
 for(unsigned i=0;i<50000;++i){for(auto& b:p)b=rng();if(controller::ble_local_parse(p,48,c)){assert(c.sequence);assert(c.op>=1&&c.op<=7);assert(c.x<=32767&&c.y<=32767);if(c.op==4)assert(c.x2<=32767&&c.y2<=32767&&c.ms>=100&&c.ms<=1200);}}
}
