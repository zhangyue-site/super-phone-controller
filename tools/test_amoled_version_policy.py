from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[1]
code=r'''
#include "version_policy.h"
#include <assert.h>
int main(void){
 const char *valid[]={"0.4.2-amoled","0.4.1-amoled","0.3.0-amoled","0.0.0-amoled","99999.1.2-amoled"};
 for(unsigned i=0;i<sizeof(valid)/sizeof(*valid);i++)assert(amoled_release_version_valid(valid[i]));
 const char *invalid[]={"","invalid","0.4.1","00.4.1-amoled","+0.4.1-amoled","0.4.1-epaper","100000.1.2-amoled","0.4.1-amoledx","0.4.-1-amoled"};
 for(unsigned i=0;i<sizeof(invalid)/sizeof(*invalid);i++)assert(!amoled_release_version_valid(invalid[i]));
 assert(!amoled_release_version_valid(0));
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(r/'firmware-amoled/main'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('Manual-confirmed AMOLED target syntax accepts newer/same/older; malformed versions rejected')
