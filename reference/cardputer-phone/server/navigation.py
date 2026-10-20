"""Fixed, reversible ADB navigation smoke test. No microphone or screen capture."""
import json,time,fcntl
from pathlib import Path
from phone import adb,focus

def wait_package(package):
    for _ in range(20):
        state=focus()
        if state.get('locked'):raise RuntimeError('Phone locked')
        if state.get('package')==package:return state
        time.sleep(.5)
    raise RuntimeError('Foreground verification failed: '+package)

def run():
    if adb('shell','getprop','ro.product.model')!='25128PNA1C':raise RuntimeError('Unexpected phone identity')
    adb('shell','input','keyevent','KEYCODE_WAKEUP')
    before=focus()
    if before.get('locked'):raise RuntimeError('Phone locked')
    adb('shell','am','start','-a','android.settings.SETTINGS')
    settings=wait_package('com.android.settings')
    time.sleep(2)
    adb('shell','input','keyevent','KEYCODE_HOME')
    home=wait_package('com.miui.home')
    return {'verified':True,'mode':'fixed_adb_automation','settings':settings,'home':home,'completed_at':time.time()}
if __name__=='__main__':
    try:
        with Path('/opt/cardputer-phone/state/task.lock').open('w') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            print(json.dumps(run()))
    except Exception as error:
        print(json.dumps({'verified':False,'error':str(error)}));raise SystemExit(2)
