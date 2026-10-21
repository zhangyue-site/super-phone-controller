"""Authenticated, per-device immutable firmware. Never exposed as public downloads."""
import hashlib,json,os,re,threading
_REPORT_LOCK=threading.Lock()
from pathlib import Path
ROOT=Path(os.environ.get('EPAPER_FIRMWARE','/var/lib/phone-controller/firmware'))
def release(device,sha=None):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',device):raise ValueError('device')
    folder=ROOT/device
    if sha is None:
        entry=json.loads((folder/'current.json').read_text())
        sha=entry['sha256']
    else:
        entry=json.loads((folder/(sha+'.json')).read_text()) if re.fullmatch(r'[0-9a-f]{64}',sha) else {}
    if not re.fullmatch(r'[0-9a-f]{64}',sha or '') or entry.get('sha256')!=sha:raise ValueError('hash')
    version=entry['version'];size=entry['size']
    if not re.fullmatch(r'[a-zA-Z0-9._-]{1,31}',version) or type(size)!=int or not 1024<=size<=0x340000:raise ValueError('metadata')
    data=(folder/(sha+'.bin')).read_bytes()
    if len(data)!=size or hashlib.sha256(data).hexdigest()!=sha:raise ValueError('artifact')
    return entry,data

def manifest(device):
    entry,_=release(device)
    return ('PCOTA1\n%d\n%s\n%s\n'%(entry['size'],entry['sha256'],entry['version'])).encode()


def report(device,raw):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',device):raise ValueError('device')
    obj=json.loads(raw)
    if not isinstance(obj,dict) or set(obj)!={'version','slot','phase','imageState'}:raise ValueError('fields')
    if not isinstance(obj['version'],str) or not re.fullmatch(r'[a-zA-Z0-9._-]{1,31}',obj['version']):raise ValueError('version')
    if obj['slot'] not in ('ota_0','ota_1') or obj['phase'] not in ('boot-confirmed','current','failed'):raise ValueError('state')
    if type(obj['imageState']) is not int or obj['imageState'] not in (-1,0,1,2,3,4,5,6):raise ValueError('image state')
    import time
    obj['receivedAt']=int(time.time())
    folder=ROOT/device;folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    # A bounded latest acknowledgement, atomic replacement; no user content.
    with _REPORT_LOCK:
        temp=folder/'report.tmp';temp.write_text(json.dumps(obj));temp.chmod(0o600);temp.replace(folder/'report.json')
    print('OTA report device=%s version=%s slot=%s phase=%s image_state=%d'%(device,obj['version'],obj['slot'],obj['phase'],obj['imageState']),flush=True)
    return obj
