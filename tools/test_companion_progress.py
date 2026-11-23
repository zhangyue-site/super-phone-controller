from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[1]
code=r"""
#include "companion_progress.h"
#include <assert.h>
int main(void){
 pc_companion s={0};
 pc_companion_begin(&s,7,"task-a");
 assert(pc_companion_apply(&s,7,1,PC_RECOGNIZE,2,7,false));
 assert(s.round==2&&s.rows[3]==PC_CURRENT&&s.rows[4]==PC_PENDING);
 assert(!pc_companion_apply(&s,6,99,PC_DONE,2,255,true));
 assert(!pc_companion_apply(&s,7,1,PC_DONE,2,255,true));
 assert(pc_companion_apply(&s,7,2,PC_DONE,2,7,false));
 assert(s.phase==PC_ERROR&&s.rows[6]!=PC_COMPLETE&&s.rows[7]!=PC_COMPLETE);
 pc_companion_begin(&s,8,"task-b");
 assert(s.rows[0]==PC_PENDING&&s.round==0);
 assert(pc_companion_apply(&s,8,1,PC_OPERATE,1,0,false));
 assert(s.rows[0]==PC_PENDING); /* no inferred history */
 pc_companion_stop(&s);
 assert(!pc_companion_apply(&s,8,2,PC_DONE,1,255,true));
 assert(s.phase==PC_STOPPING);
 pc_companion_begin(&s,9,"task-c");
 assert(pc_companion_apply(&s,9,1,PC_DONE,1,127,true));
 assert(s.phase==PC_DONE&&s.rows[7]==PC_COMPLETE);
 assert(!pc_companion_apply(&s,9,2,PC_OPERATE,2,0,false));
 pc_companion_begin(&s,10,"task-d");
 assert(pc_companion_apply(&s,10,1,PC_RECOGNIZE,2,7,false));
 assert(pc_companion_apply(&s,10,2,PC_DISPATCH,2,15,false));
 assert(pc_companion_apply(&s,10,3,PC_OPERATE,2,31,false));
 assert(pc_companion_apply(&s,10,4,PC_RECOGNIZE,3,7,false));
 assert(s.rows[4]==PC_PENDING&&s.rows[5]==PC_PENDING); /* current round */
 return 0;
}
"""
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=c11','-Wall','-Werror','-fsanitize=address,undefined','-I',str(r/'firmware-amoled/main'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('Companion state: old epochs/revisions, STOP, unverified done, fresh rounds passed')
