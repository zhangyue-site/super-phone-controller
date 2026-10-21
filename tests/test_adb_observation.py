"""Execute the firmware's actual fixed shell observation script against Android command fixtures."""
import ast,re,subprocess,unittest,tempfile,os
from pathlib import Path
from unittest.mock import patch
from display_service.dialogue import parse_observation
ROOT=Path(__file__).resolve().parents[1]
def script():
 text=(ROOT/'firmware-epaper/main/adb_local.cpp').read_text().split('static const char observation_command[]=')[1].split(';\nstatic bool shell_command')[0]
 return ''.join(ast.literal_eval(x) for x in re.findall(r'"(?:\\.|[^"\\])*"',text))
BASE='''
dumpsys(){ if [ "$1" = window ]; then POLICY; else echo 'topResumedActivity=ActivityRecord{abc u0 com.android.settings/.Settings t1}'; fi; }
wm(){ echo 'Physical size: 1080x2400'; }
cmd(){ echo 'com.miui.home/.launcher.Launcher'; }
uiautomator(){ for target do :; done; printf '<?xml version="1.0"?><hierarchy><node package="com.android.settings" text="设置" bounds="[0,0][200,200]"/></hierarchy>\\n' > \"$target\"; }
'''
class ObservationTests(unittest.TestCase):
 def setUp(self):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
  env=patch.dict(os.environ,{'TMPDIR':temp.name});env.start();self.addCleanup(env.stop)

 def test_real_firmware_script_observation_parses(self):
  result=subprocess.run(['sh','-c',BASE.replace('POLICY',"echo 'showing=false'")+script()],capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stderr)
  self.assertEqual(parse_observation(result.stdout)['package'],'com.android.settings')
 def test_unknown_and_failed_policy_never_report_unlocked(self):
  for body in ['return 1',"echo 'permission denied'", "echo 'showing=true'"]:
   r=subprocess.run(['sh','-c',BASE.replace('POLICY',body)+script()],capture_output=True,text=True)
   with self.assertRaises(ValueError):parse_observation(r.stdout)

 def test_android_dump_writes_file_not_callers_stdout(self):
  # The real Android command prints only a status line. The XML goes to the
  # requested file in a separate process, so /proc/self/fd/1 is not our stdout.
  fixture=BASE.replace('POLICY',"echo 'showing=false'")
  fixture=fixture[:fixture.index('uiautomator(){')]+"""
uiautomator(){
 for target do :; done
 if [ \"$target\" != /proc/self/fd/1 ]; then
  printf '<?xml version=\"1.0\"?><hierarchy><node package=\"com.android.settings\" text=\"设置\" bounds=\"[0,0][200,200]\"/></hierarchy>\\n' > \"$target\"
 fi
 printf 'UI hierchary dumped to: %s\\n' \"$target\"
}
"""
  with tempfile.TemporaryDirectory() as temp:
   r=subprocess.run(['sh','-c',fixture+script()],capture_output=True,text=True,env=dict(os.environ,TMPDIR=temp))
   self.assertEqual(r.returncode,0,r.stderr)
   self.assertEqual(parse_observation(r.stdout)['package'],'com.android.settings')
   self.assertEqual(list(Path(temp).iterdir()),[])
 def test_verbose_activity_output_filtered_before_limit(self):
  fixture=BASE.replace('POLICY',"echo 'showing=false'")
  fixture+='\ncmd(){\n if [ "$2" = resolve-activity ]; then echo com.miui.home/.launcher.Launcher; return; fi\n echo \'150 activities found:\'\n i=0;while [ "$i" -lt 150 ]; do\n  printf \'Activity #%s:\\npriority=0 preferredOrder=0\\ncom.example.app%s/.Main\\n\' "$i" "$i"\n  i=$((i+1))\n done\n}\n'
  r=subprocess.run(['sh','-c',fixture+script()],capture_output=True,text=True)
  self.assertEqual(len(parse_observation(r.stdout)['apps']),128)
 def test_observation_fits_firmware_service_buffer(self):
  self.assertLess(len(('shell:'+script()+'; echo __PC_EXIT_$?__').encode())+1,2048)
