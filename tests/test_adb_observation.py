"""Execute the firmware's actual fixed shell observation script against Android command fixtures."""
import ast,re,subprocess,unittest
from pathlib import Path
from display_service.dialogue import parse_observation
ROOT=Path(__file__).resolve().parents[1]
def script():
 text=(ROOT/'firmware-epaper/main/adb_local.cpp').read_text().split('static const char observation_command[]=')[1].split(';\nstatic bool shell_command')[0]
 return ''.join(ast.literal_eval(x) for x in re.findall(r'"(?:\\.|[^"\\])*"',text))
BASE='''
dumpsys(){ if [ "$1" = window ]; then POLICY; else echo 'topResumedActivity=ActivityRecord{abc u0 com.android.settings/.Settings t1}'; fi; }
wm(){ echo 'Physical size: 1080x2400'; }
cmd(){ echo 'com.miui.home/.launcher.Launcher'; }
uiautomator(){ printf '<?xml version="1.0"?><hierarchy><node package="com.android.settings" text="设置" bounds="[0,0][200,200]"/></hierarchy>\\n'; }
'''
class ObservationTests(unittest.TestCase):
 def test_real_firmware_script_observation_parses(self):
  result=subprocess.run(['sh','-c',BASE.replace('POLICY',"echo 'showing=false'")+script()],capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stderr)
  self.assertEqual(parse_observation(result.stdout)['package'],'com.android.settings')
 def test_unknown_and_failed_policy_never_report_unlocked(self):
  for body in ['return 1',"echo 'permission denied'", "echo 'showing=true'"]:
   r=subprocess.run(['sh','-c',BASE.replace('POLICY',body)+script()],capture_output=True,text=True)
   with self.assertRaises(ValueError):parse_observation(r.stdout)
