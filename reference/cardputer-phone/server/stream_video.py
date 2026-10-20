"""Continuous built-in H.264 stream, decoded on Linux; never runs screencap."""
import os,subprocess,time,signal
from pathlib import Path
ROOT=Path('/opt/cardputer-phone');ROOT.joinpath('state').mkdir(exist_ok=True)
ADB='/opt/android-sdk/platform-tools/adb'
env=dict(os.environ,HOME=str(ROOT/'home'))
base=[ADB,'-P','15037']
def run(*args,timeout=12):return subprocess.run(base+list(args),env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
run('start-server')
# Only this dedicated transport is reset: after a board reboot, the ADB daemon
# can still list its old TCP connection as "device" while shell returns closed.
run('disconnect','127.0.0.1:15565');run('connect','127.0.0.1:15565',timeout=20)
if run('-s','127.0.0.1:15565','get-state').stdout.strip()!=b'device':raise SystemExit('ADB phone transport not ready')
if run('-s','127.0.0.1:15565','shell','getprop','ro.product.model').stdout.strip()!=b'25128PNA1C':raise SystemExit('Unexpected phone model; refusing capture')
ROOT.joinpath('state/latest.jpg').unlink(missing_ok=True)
video=subprocess.Popen(base+['-s','127.0.0.1:15565','exec-out','screenrecord','--output-format=h264','--size','480x1040','--bit-rate','500000','--time-limit','0','-'],env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
decode=subprocess.Popen(['/usr/bin/ffmpeg','-hide_banner','-loglevel','warning','-probesize','32768','-analyzeduration','0','-fflags','+genpts','-use_wallclock_as_timestamps','1','-f','h264','-i','pipe:0','-vf',"select='isnan(prev_selected_t)+gte(t-prev_selected_t,0.75)'",'-fps_mode','vfr','-q:v','4','-update','1','-atomic_writing','1','-y',str(ROOT/'state/latest.jpg')],stdin=video.stdout,stdout=subprocess.DEVNULL)
video.stdout.close()
def stop(*_):
    for process in (video,decode):
        if process.poll() is None:process.terminate()
signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
try:
    while video.poll() is None and decode.poll() is None:time.sleep(.3)
finally:
    stop()
    for p in (video,decode):
        try:p.wait(timeout=4)
        except subprocess.TimeoutExpired:p.kill()
raise SystemExit(1)
