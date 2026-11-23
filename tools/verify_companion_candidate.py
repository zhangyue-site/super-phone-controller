"""Run candidate-only host regressions; never accesses a real board or live service."""
from pathlib import Path
import argparse,subprocess,json,sys
r=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--cjson-dir',type=Path,default=r/'evidence/cjson');p.add_argument('--output-dir',type=Path,default=r/'evidence/verification');a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
names=['test_amoled_registry.py','test_amoled_control.py','test_amoled_ota.py','test_amoled_power.py','test_amoled_version_policy.py','test_amoled_interlock.py','test_amoled_wifi_worker.py','test_amoled_wifi.py','test_amoled_wifi_transport.py','test_amoled_wifi_ingress.py','test_amoled_direct.py','test_amoled_direct_owner.py','test_amoled_direct_disconnect.py','test_amoled_audio.py','test_amoled_audio_owner.py','test_amoled_plugin.py','test_amoled_plugin_transport.py','test_amoled_direct_runtime.py','test_amoled_direct_transport.py','check_amoled_plugin_syntax.py','check_amoled_direct_syntax.py','test_companion_progress.py','test_companion_observers.py','test_amoled_font.py','test_amoled_display_idle.py','test_amoled_display_memory.py','test_amoled_console_liveness.py']
json_tests={'test_amoled_plugin.py','test_amoled_plugin_transport.py','test_amoled_direct_runtime.py','test_amoled_direct_transport.py','check_amoled_plugin_syntax.py','check_amoled_direct_syntax.py'}
commands=[]
for name in names:
 args=[sys.executable,'tools/'+name]
 if name=='test_amoled_registry.py':args+=['--output-dir',str(a.cjson_dir)]
 elif name in json_tests:args+=['--cjson-dir',str(a.cjson_dir)]
 elif name in {'test_amoled_display_memory.py','test_amoled_console_liveness.py'}:args+=[str(r)]
 commands.append((name,args))
for pattern in ['test_remote*.py','test_companion*.py','test_plugin*.py','test_dialogue.py']:
 commands.append((pattern,[sys.executable,'-m','unittest','discover','-s','tests','-p',pattern]))
results=[]
with (a.output_dir/'checks.log').open('w') as log:
 for name,args in commands:
  result=subprocess.run(args,cwd=r,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
  log.write(name+'\n'+result.stdout+'\n');log.flush();results.append({'check':name,'exit':result.returncode})
(a.output_dir/'checks.json').write_text(json.dumps(results,indent=2))
print(json.dumps({'checks':len(results),'passed':sum(x['exit']==0 for x in results),'failed':[x for x in results if x['exit']]}))
raise SystemExit(any(x['exit'] for x in results))
