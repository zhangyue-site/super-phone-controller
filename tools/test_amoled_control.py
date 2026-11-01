"""Host checks for actual AMOLED control packet bounds and ASCII HID encoding."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
def function(text,name):
 start=text.index('static bool '+name+'(');brace=text.index('{',start);depth=1;end=brace+1
 while depth:
  depth+=(text[end]=='{')-(text[end]=='}');end+=1
 return text[start:end]
source='#include <stdint.h>\n#include <stdbool.h>\n#include <stddef.h>\n#include <assert.h>\n#include <string.h>\n#include <stdio.h>\ntypedef struct {uint8_t op;uint32_t sequence,epoch;uint16_t a[5];} Work;\n'
source+=function((root/'firmware-amoled/main/relay.c').read_text(),'parse')+'\n'
source+=function((root/'firmware-amoled/main/usb.c').read_text(),'ascii_key')+'\n'
source+=r"""
int main(void){
 uint8_t p[48]={1,3,1};Work w;
 assert(parse(p,&w));p[6]=255;p[7]=127;assert(parse(p,&w));p[7]=128;assert(!parse(p,&w));p[7]=0;p[10]=1;assert(!parse(p,&w));
 memset(p,0,48);p[0]=1;p[1]=4;p[2]=1;p[14]=100;assert(parse(p,&w));p[14]=99;assert(!parse(p,&w));p[14]=176;p[15]=4;assert(parse(p,&w));p[14]=177;assert(!parse(p,&w));
 memset(p,0,48);p[0]=1;p[1]=14;p[2]=1;p[6]=1;p[8]='9';assert(parse(p,&w));p[9]='0';assert(!parse(p,&w));p[6]=2;assert(parse(p,&w));p[6]=9;assert(!parse(p,&w));p[6]=2;p[8]=31;assert(!parse(p,&w));
 const char *groups[]={"abcdefghijklmnopqrstuvwxyz","ABCDEFGHIJKLMNOPQRSTUVWXYZ","1234567890","!@#$%^&*()"," -=[]\\;'/.,`","_+{}|:\"?><~"};
 const uint8_t keys[][26]={{4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29},{4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29},{30,31,32,33,34,35,36,37,38,39},{30,31,32,33,34,35,36,37,38,39},{44,45,46,47,48,49,51,52,56,55,54,53},{45,46,47,48,49,51,52,56,55,54,53}};
 int checked=0;for(int g=0;g<6;g++)for(int i=0;groups[g][i];i++){uint8_t m=99,k=0;assert(ascii_key(groups[g][i],&m,&k));assert(k==keys[g][i]);assert(m==((g==1||g==3||g==5)?2:0));checked++;}assert(checked==95);
 uint8_t m,k;assert(!ascii_key(31,&m,&k));assert(!ascii_key(127,&m,&k));puts("Packet bounds and all 95 printable ASCII encodings passed");
}
"""
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(source)
 subprocess.run(['cc','-std=c11','-fsanitize=address,undefined','-g',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)

