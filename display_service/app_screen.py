"""Opt-in screen frames authorized by a separate BLE-possession capability.
No phone actions, device bearer keys, screenshots on disk, or ADB access.
"""
import json,re,threading,os,hashlib,hmac,secrets
from .app_ota import Authority
from .screen_state import ScreenStates
from .conversation import CONVERSATION
from .wechat_nav import STORE
AUTHORITY=Authority()
SCREEN_STATES=ScreenStates()
LOCK=threading.Lock()
SEQUENCES={}
USB_AUTHORITY=Authority()
def usb_challenge(device,serial,keys):
 if not isinstance(serial,str) or not re.fullmatch("[0-9A-Fa-f]{12}",serial):raise ValueError("serial")
 result=USB_AUTHORITY.challenge(device,keys)
 with USB_AUTHORITY.lock:
  item=USB_AUTHORITY.challenges[result["challenge"]]
  USB_AUTHORITY.challenges[result["challenge"]]=(*item,serial.upper())
 result.update(serial=serial.upper(),protocol="pcusb-v1")
 return result
def usb_authorize(device,serial,nonce,proof,keys):
 if not isinstance(serial,str) or not re.fullmatch("[0-9A-Fa-f]{12}",serial):raise ValueError("serial")
 if not isinstance(nonce,str) or not re.fullmatch("[0-9a-f]{64}",nonce) or not isinstance(proof,str) or not re.fullmatch("[0-9a-f]{64}",proof):raise ValueError("proof")
 with USB_AUTHORITY.lock:
  USB_AUTHORITY._prune(USB_AUTHORITY.clock());item=USB_AUTHORITY.challenges.pop(nonce,None)
  if item is None or item[1]!=device or item[2]!=serial.upper() or device not in keys:raise ValueError("challenge")
  message=b"pcusb-v1\n"+device.encode()+b"\n"+serial.upper().encode()+b"\n"+bytes.fromhex(nonce)
  if not hmac.compare_digest(proof,hmac.new(keys[device].encode(),message,hashlib.sha256).hexdigest()):raise ValueError("proof")
 with AUTHORITY.lock:
  AUTHORITY._prune(AUTHORITY.clock())
  if len(AUTHORITY.tickets)>=256:raise ValueError("rate")
  ticket=secrets.token_urlsafe(32);AUTHORITY.tickets[ticket]=(AUTHORITY.clock()+300,device,"usb-screen")
 return {"ticket":ticket,"expiresIn":300,"device":device,"serial":serial.upper(),"protocol":"pcusb-v1","scope":"screen-frames"}



def usb_renew(ticket,obj,keys):
 if not isinstance(obj,dict) or set(obj)!={'device','serial','challenge','proof'}:raise ValueError('fields')
 device=subject(ticket)
 if device!=obj['device']:raise ValueError('device')
 grant=usb_authorize(device,obj['serial'],obj['challenge'],obj['proof'],keys)
 with AUTHORITY.lock:
  now=AUTHORITY.clock();AUTHORITY._prune(now)
  AUTHORITY.tickets.pop(grant['ticket'],None)
  item=AUTHORITY.tickets.get(ticket)
  if item is None or item[1]!=device:raise ValueError('revoked')
  AUTHORITY.tickets[ticket]=(now+300,device,'usb-screen')
 return {'expiresIn':300,'scope':'screen-frames','protocol':'pcusb-v1'}


def extend_diagnostic_ticket(device,grant):
 if device!='epaper-01' or os.environ.get('EPAPER_SCREEN_DIAG_LONG')!='epaper-01':return
 item=AUTHORITY.tickets.get(grant['ticket'])
 if item is None or item[1]!=device:raise ValueError('ticket')
 AUTHORITY.tickets[grant['ticket']]=(AUTHORITY.clock()+1200,item[1],item[2]);grant['expiresIn']=1200

def subject(ticket):
 if not isinstance(ticket,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',ticket):raise ValueError('ticket')
 with AUTHORITY.lock:
  AUTHORITY._prune(AUTHORITY.clock());item=AUTHORITY.tickets.get(ticket)
  if item is None:raise ValueError('ticket')
  return item[1]

def _obsolete_frame_response(mailbox,device,ticket,previous,barrier):
 # Caller holds AUTHORITY then mailbox lock. A stale payload is never accepted.
 item=AUTHORITY.tickets.get(ticket)
 if item is None or item[0]<=AUTHORITY.clock() or item[1]!=device:raise ValueError('revoked')
 if previous.screen_session!=ticket:raise ValueError('screen session changed')
 current=mailbox.jobs.get(device)
 if current is previous and not previous.done and not previous.cancelled and previous.video_barrier==barrier:return None
 if current is not None and current.screen_session and current.screen_session!=ticket:return None
 active=current is not None and not current.done and not current.cancelled
 same_source=active and current.screen_session==ticket
 return {'accepted':False,'reason':'superseded frame' if active else 'no active voice task','barrier':current.video_barrier if same_source else '0'*32}

def handle(handler,config):
 path=handler.path
 if path not in ('/app-screen/challenge','/app-screen/authorize','/app-screen/usb-challenge','/app-screen/usb-authorize','/app-screen/usb-renew','/app-screen/frame','/app-screen/stop','/app-screen/status'):return False
 try:
  if handler.command!='POST':handler.reply(405,b'{}');return True
  size=int(handler.headers.get('Content-Length','0'))
  if path in ('/app-screen/challenge','/app-screen/authorize','/app-screen/usb-challenge','/app-screen/usb-authorize','/app-screen/usb-renew'):
   if not 1<=size<=1024:raise ValueError('size')
   raw=handler.rfile.read(size)
   if len(raw)!=size:raise ValueError('truncated')
   obj=json.loads(raw);keys=json.loads(config.read_text())
   if not isinstance(obj,dict):raise ValueError('body')
   if path.endswith('/usb-renew'):
    header=handler.headers.get('Authorization','')
    if not header.startswith('Bearer '):raise ValueError('auth')
    result=usb_renew(header[7:],obj,keys)
   elif path.endswith('/usb-challenge'):
    if set(obj)!={'device','serial'}:raise ValueError('fields')
    result=usb_challenge(obj['device'],obj['serial'],keys)
   elif path.endswith('/usb-authorize'):
    if set(obj)!={'device','serial','challenge','proof'}:raise ValueError('fields')
    result=usb_authorize(obj['device'],obj['serial'],obj['challenge'],obj['proof'],keys)
    with AUTHORITY.lock:
     for old,item in list(AUTHORITY.tickets.items()):
      if item[1]==obj['device'] and old!=result['ticket']:AUTHORITY.tickets.pop(old,None)
     SCREEN_STATES.prune(AUTHORITY.tickets,AUTHORITY.clock())
     CONVERSATION.mailbox.cancel(obj['device'])
   elif path.endswith('/challenge'):
    if set(obj)!={'device'}:raise ValueError('fields')
    result=AUTHORITY.challenge(obj['device'],keys)
   else:
    if set(obj)!={'device','challenge','proof'}:raise ValueError('fields')
    grant=AUTHORITY.authorize(obj['device'],obj['challenge'],obj['proof'],keys)
    with AUTHORITY.lock:
     extend_diagnostic_ticket(obj['device'],grant)
     for old,item in list(AUTHORITY.tickets.items()):
      if item[1]==obj['device'] and old!=grant['ticket']:AUTHORITY.tickets.pop(old,None)
     SCREEN_STATES.prune(AUTHORITY.tickets,AUTHORITY.clock())
     CONVERSATION.mailbox.cancel(obj['device'])
    result={'ticket':grant['ticket'],'expiresIn':grant['expiresIn'],'scope':'screen-frames'}
   handler.reply(200,json.dumps(result).encode());return True
  header=handler.headers.get('Authorization','')
  if not header.startswith('Bearer '):raise ValueError('auth')
  ticket=header[7:];device=subject(ticket)
  mailbox=CONVERSATION.mailbox
  if path.endswith('/status'):
   if size!=0:raise ValueError('size')
   # Recheck while holding the capture authority lock, then mailbox: revoke
   # and authorize use the same lock order. Never cache a terminal globally.
   with AUTHORITY.lock:
    AUTHORITY._prune(AUTHORITY.clock());item=AUTHORITY.tickets.get(ticket)
    if item is None or item[1]!=device:raise ValueError('revoked')
    SCREEN_STATES.record(ticket,device,handler.headers,AUTHORITY.clock(),AUTHORITY.tickets)
    with mailbox.lock:
     j=mailbox.jobs.get(device)
     if j and (j.cancelled or (j.done and getattr(j,'screen_session','')!=ticket)):j=None
     if j and mailbox.jobs.get(device) is j and j.device==device and not j.done and not j.cancelled:
      SCREEN_STATES.bind_job(j,ticket,device,AUTHORITY.clock(),AUTHORITY.tickets)
     result={'state':j.state if j else 'idle','reply':j.reply if j else '',
      'frame':j.video_sequence if j else 0,'pointerReady':bool(j and j.pointer_protocol=='absolute-v1'),
      'skills':STORE.catalog(device),'barrier':j.video_barrier if j else '',
      'accessibilityProtocol':1,
      'verified':bool(j and j.done and j.state=='done' and getattr(j,'navigation_verified',False) is True)}
   handler.reply(200,json.dumps(result,ensure_ascii=False).encode());return True
  if path.endswith('/stop'):
   if size!=0:raise ValueError('size')
   with AUTHORITY.lock:
    if ticket not in AUTHORITY.tickets:raise ValueError('revoked')
    AUTHORITY.tickets.pop(ticket,None)
    SCREEN_STATES.discard(ticket)
    with LOCK:SEQUENCES.pop(ticket,None)
    mailbox.cancel(device);STORE.invalidate(device)
   handler.reply(200,b'{}');return True
  from . import accessibility
  kind=handler.headers.get('Content-Type')
  if kind not in ('image/jpeg',accessibility.CONTENT_TYPE) or not 1<=size<=(524288 if kind=='image/jpeg' else accessibility.MAX_ENVELOPE):raise ValueError('size')
  platform=handler.headers.get('X-Screen-Platform','android')
  if platform not in ('android','ios'):raise ValueError('capture platform')
  sequence=int(handler.headers.get('X-Screen-Sequence','0'))
  if not 1<=sequence<=2147483647:raise ValueError('sequence')
  payload=handler.rfile.read(size)
  if len(payload)!=size:raise ValueError('truncated')
  payload,ui_tree=accessibility.decode_frame(kind,payload,int(handler.headers.get('X-Screen-Native-Width','0')),int(handler.headers.get('X-Screen-Native-Height','0')))
  if platform!='android':ui_tree=None
  with AUTHORITY.lock:
   AUTHORITY._prune(AUTHORITY.clock())
   if ticket not in AUTHORITY.tickets:raise ValueError('revoked')
   with LOCK:
    for key in list(SEQUENCES):
     if key not in AUTHORITY.tickets:SEQUENCES.pop(key,None)
    if sequence<=SEQUENCES.get(ticket,0):raise ValueError('stale frame')
    SEQUENCES[ticket]=sequence
   with mailbox.lock:
    j=mailbox.jobs.get(device)
    if j is None or j.done or j.cancelled:
     handler.reply(202,b'{"accepted":false,"reason":"no active voice task","barrier":"00000000000000000000000000000000"}');return True
    if j.screen_session and j.screen_session!=ticket:raise ValueError('screen session changed')
    j.screen_session=ticket
    if j.fenced and handler.headers.get('X-Screen-Barrier','')!=j.video_barrier:
     handler.reply(202,json.dumps({'accepted':False,'reason':'capture barrier required','barrier':j.video_barrier}).encode());return True
    if getattr(j,'video_platform','') and j.video_platform!=platform:raise ValueError('capture platform changed')
    capture_barrier=j.video_barrier
    voice_session,voice_sequence,frame_sequence=j.session,j.sequence,j.video_sequence+1
   try:
    result=mailbox.ingest_video(device,voice_session,voice_sequence,frame_sequence,payload,'jpeg',expected_barrier=capture_barrier,source='user-consented-app-screen',platform=platform)
   except ValueError as error:
    if str(error) in ('unknown turn','turn cancelled or expired','capture barrier required','capture superseded','video superseded'):
     with mailbox.lock:
      obsolete=_obsolete_frame_response(mailbox,device,ticket,j,capture_barrier)
      if obsolete is not None:
       handler.reply(202,json.dumps(obsolete).encode());return True
    raise
   with mailbox.lock:
    obsolete=_obsolete_frame_response(mailbox,device,ticket,j,capture_barrier)
    if obsolete is not None:
     handler.reply(202,json.dumps(obsolete).encode());return True
    if mailbox._job(device,voice_session,voice_sequence) is not j or j.done or j.video_barrier!=capture_barrier:raise ValueError('superseded')
    if getattr(j,'video_platform','') and j.video_platform!=platform:raise ValueError('capture platform changed')
    j.video_source='user-consented-app-screen'
    if ui_tree and (ui_tree['width'],ui_tree['height'])!=(j.video_width,j.video_height):ui_tree=None
    accessibility.bind(j,ui_tree,j.video,capture_barrier,frame_sequence)
    result['barrier']=j.video_barrier
  result['source']='user-consented-app-screen'
  if frame_sequence==1 or frame_sequence%10==0:print('APP_SCREEN frame device=%s turn=%d frame=%d width=%d height=%d'%(device,voice_sequence,frame_sequence,result['width'],result['height']),flush=True)
  handler.reply(200,json.dumps(result).encode())
 except (ValueError,TypeError,KeyError,OSError):handler.reply(403,b'{"error":"screen session invalid or expired"}')
 return True
