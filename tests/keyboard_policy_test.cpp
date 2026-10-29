#include <cassert>
#include "ble_local_policy.h"
int main(){
 assert(controller::keyboard_before_deadline(7499999,7500000));assert(!controller::keyboard_before_deadline(7500000,7500000));assert(!controller::keyboard_before_deadline(7500001,7500000));
 uint8_t report[9]={1,2,0,4};
 assert(controller::keyboard_completed(4,0,report,9,2,4)==2);
 assert(controller::keyboard_completed(4,1,report,9,2,4)==4);
 assert(controller::keyboard_completed(4,0,report,8,2,4)==4);
 assert(controller::keyboard_completed(5,0,report,9,2,4)==5);
 assert(controller::keyboard_completed(-1,0,report,9,2,4)==-1);
 report[1]=report[3]=0;assert(controller::keyboard_completed(5,0,report,9,2,4)==3);
 assert(controller::keyboard_completed(4,0,report,9,2,4)==4);
 for(unsigned c=0x20;c<=0x7e;++c){uint8_t m,k;assert(controller::ascii_key(c,m,k));assert(k&&m<=2);}
 uint8_t modifier,usage;assert(controller::ascii_key('A',modifier,usage)&&modifier==2&&usage==4);
 assert(controller::ascii_key('?',modifier,usage)&&modifier==2&&usage==0x38);
 assert(controller::ascii_key('"',modifier,usage)&&modifier==2&&usage==0x34);
 assert(controller::ascii_key('\\',modifier,usage)&&modifier==0&&usage==0x31);
 assert(!controller::ascii_key(10,modifier,usage));assert(!controller::ascii_key(127,modifier,usage));
 uint8_t p[48]={1,13,1};controller::BleLocalPacket out;
 for(unsigned k=0;k<256;++k){p[6]=255;p[8]=k;bool accepted=controller::ble_local_parse(p,48,out);assert(accepted==((k>=4&&k<=0x2c)||(k>=0x4f&&k<=0x52)));}
 p[7]=1;p[8]=4;assert(!controller::ble_local_parse(p,48,out));p[7]=0;
 p[6]=2;p[8]=4;assert(controller::ble_local_parse(p,48,out));p[8]=0x66;assert(!controller::ble_local_parse(p,48,out));
 p[1]=14;p[6]=1;p[8]='a';assert(controller::ble_local_parse(p,48,out));p[9]='b';assert(!controller::ble_local_parse(p,48,out));p[6]=2;assert(controller::ble_local_parse(p,48,out));p[9]=10;assert(!controller::ble_local_parse(p,48,out));
 p[1]=8;p[6]=4;p[8]=p[9]=0;assert(controller::ble_local_parse(p,48,out));p[1]=9;p[6]=0;assert(controller::ble_local_parse(p,48,out));
}
