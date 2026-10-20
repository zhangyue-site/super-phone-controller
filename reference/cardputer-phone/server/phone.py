"""Scoped OpenClaw phone tools. Observe video frames; control using ADB only."""
import argparse,hashlib,json,os,subprocess,time,fcntl
from pathlib import Path
ROOT=Path('/opt/cardputer-phone');STATE=ROOT/'state';STATE.mkdir(exist_ok=True)
ADB='/opt/android-sdk/platform-tools/adb';SERIAL='127.0.0.1:15565'

def adb(*args):
    r=subprocess.run([ADB,'-P','15037','-s',SERIAL,*args],env=dict(os.environ,HOME=str(ROOT/'home')),capture_output=True,timeout=12)
    if r.returncode:raise RuntimeError('ADB command failed: '+r.stderr.decode(errors='replace')[:180])
    return r.stdout.decode(errors='replace').strip()
def frame():
    p=STATE/'latest.jpg'
    if not p.exists() or time.time()-p.stat().st_mtime>8:raise RuntimeError('Live video frame unavailable or stale')
    before=focus();image=p.read_bytes();after=focus()
    if before!=after:raise RuntimeError('Foreground changed during observation; observe again')
    obs=hashlib.sha256(image+str(time.time_ns()).encode()).hexdigest()[:32]
    # A stable copy is important: AI may read it after the next live frame arrives.
    stable=STATE/'observation.jpg';stable.write_bytes(image)
    (STATE/'observation.json').write_text(json.dumps({'id':obs,'created':time.time()}))
    return {'observation_id':obs,'image':str(stable),'frame_width':480,'frame_height':1040,
            'coordinates':'integers 0..1000 over the full displayed image',
            'route':'phone H264 → ESP32 → TLS → Linux decode','bytes':len(image),'foreground':after,'captured_at':time.time()}
def consume(token):
    p=STATE/'observation.json';v=json.loads(p.read_text())
    if not token or token!=v.get('id') or time.time()-v.get('created',0)>45:raise ValueError('Observe a new video frame before input')
    p.unlink()
def coordinate(value):
    value=int(value)
    if not 0<=value<=1000:raise ValueError('Coordinates must be 0..1000')
    return value
def native_size():
    import re
    values=re.findall(r'(\d+)x(\d+)',adb('shell','wm','size'))
    if not values:raise RuntimeError('Phone display size unavailable')
    return tuple(map(int,values[-1]))
def focus():
    import re
    value=adb('shell','dumpsys activity activities | grep -m 1 topResumedActivity || true')
    policy=adb('shell',"dumpsys window policy | grep -E 'showing=|inputRestricted=' || true")
    locked=bool(re.search(r'\bshowing=true\b',policy))
    match=re.search(r'\bu\d+\s+([A-Za-z0-9_.]+)/([^\s}]+)',value)
    if not match:return {'package':None,'activity':None,'locked':locked,'note':'No resumed app; screen may be locked or asleep'}
    return {'package':match.group(1),'activity':match.group(2),'locked':locked}
def main():
    parser=argparse.ArgumentParser();parser.add_argument('op',choices=['status','frame','describe','focus','wake','key','tap','swipe']);parser.add_argument('values',nargs='*');parser.add_argument('--observation');parser.add_argument('--goal',default='描述当前手机界面')
    args=parser.parse_args()
    with (STATE/'controller.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if args.op=='status':result={'adb':adb('get-state'),'model':adb('shell','getprop','ro.product.model'),'frame_live':(STATE/'latest.jpg').exists() and time.time()-(STATE/'latest.jpg').stat().st_mtime<8}
        elif args.op=='frame':result=frame()
        elif args.op=='focus':result=focus()
        elif args.op=='wake':
            # An explicitly requested task may wake an idle screen, never unlock it.
            adb('shell','input','keyevent','KEYCODE_WAKEUP');result={'wake_submitted':True,'unlocked':False}
        elif args.op=='describe':
            from vision import describe
            result=frame();result.update(describe(Path(result['image']).read_bytes(),args.goal))
        else:
            values=args.values
            if args.op=='key':
                if len(values)!=1 or values[0] not in ('HOME','BACK','WAKEUP'):raise ValueError('Allowed keys: HOME, BACK, WAKEUP')
            else:
                expected=2 if args.op=='tap' else 4
                if len(values)!=expected:raise ValueError('Incorrect coordinate count')
                values=list(map(coordinate,values))
            consume(args.observation)
            if args.op=='key':adb('shell','input','keyevent','KEYCODE_'+values[0])
            else:
                w,h=native_size();points=[str(round(v*((w-1) if i%2==0 else (h-1))/1000)) for i,v in enumerate(values)]
                adb('shell','input',args.op,*points,*(['500'] if args.op=='swipe' else []))
            with (STATE/'input-audit.jsonl').open('a') as audit:
                audit.write(json.dumps({'time':time.time(),'action':args.op,'values':values,'observation':args.observation,'submitted':True})+'\n')
            result={'submitted':True,'verification':'Read a new live frame before continuing. Input was not retried.'}
        print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
