#pragma once
#include <stdint.h>
#include <stddef.h>
namespace controller {
inline bool keyboard_usage(uint16_t usage){return (usage>=0x04&&usage<=0x2c)||(usage>=0x4f&&usage<=0x52);}
inline bool ascii_key(uint8_t c,uint8_t& modifier,uint8_t& usage){
 modifier=0;usage=0;
 if(c>='a'&&c<='z'){usage=4+c-'a';return true;}
 if(c>='A'&&c<='Z'){modifier=2;usage=4+c-'A';return true;}
 if(c>='1'&&c<='9'){usage=0x1e + c-'1';return true;}
 if(c=='0'){usage=0x27;return true;}
 const char plain[]=" -=[]\\;'/`",shift[]=" _+{}|:\"?~";
 const uint8_t codes[]={0x2c,0x2d,0x2e,0x2f,0x30,0x31,0x33,0x34,0x38,0x35};
 for(size_t i=0;i<sizeof(codes);++i){if(c==plain[i]){usage=codes[i];return true;}if(c==shift[i]){modifier=2;usage=codes[i];return true;}}
 const char symbols[]="!@#$%^&*()";
 for(unsigned i=0;i<10;++i)if(c==symbols[i]){modifier=2;usage=0x1e + i;return true;}
 if(c==','||c=='.'||c=='<'||c=='>'){modifier=(c=='<'||c=='>')?2:0;usage=(c==','||c=='<')?0x36:0x37;return true;}
 return false;
}
inline bool ascii_packet(uint16_t length,const uint16_t words[4]){
 if(length<1||length>8)return false;
 for(unsigned i=0;i<8;++i){uint8_t c=words[i/2]>>(8*(i%2));if(i<length){if(c<0x20||c>0x7e)return false;}else if(c)return false;}
 return true;
}
}
namespace controller {
inline bool keyboard_before_deadline(int64_t now,int64_t deadline){return now<deadline;}
// States: 4 press in flight, 2 press complete, 5 release in flight, 3 released.
inline int keyboard_completed(int state,uint8_t instance,const uint8_t* report,size_t length,uint8_t modifier,uint8_t usage){
 if(!report||instance!=0||length!=9||report[0]!=1)return state;
 if(state==4&&report[1]==modifier&&report[2]==0&&report[3]==usage){for(unsigned i=4;i<9;++i)if(report[i])return state;return 2;}
 if(state==5){for(unsigned i=1;i<9;++i)if(report[i])return state;return 3;}
 return state;
}
}
