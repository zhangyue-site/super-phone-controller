"""Opt-in screen frames authorized by a separate BLE-possession capability.
No phone actions, device bearer keys, screenshots on disk, or ADB access.
"""
import json,re,threading
from .app_ota import Authority
from .conversation import CONVERSATION
AUTHORITY=Authority()
LOCK=threading.Lock()
SEQUENCES={}

def subject(ticket):
 if not isinstance(ticket,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',ticket):raise ValueError('ticket')
 with AUTHORITY.lock:
  AUTHORITY._prune(AUTHORITY.clock());item=AUTHORITY.tickets.get(ticket)
  if item is None:raise ValueError('ticket')
  return item[1]

def handle(handler,config):
 path=handler.path
 if path not in ('/app-screen/challenge','/app-screen/authorize','/app-screen/frame','/app-screen/stop'):return False
 try:
  if handler.command!='POST':handler.reply(405,b'{}');return True
  size=int(handler.headers.get('Content-Length','0'))
  if path in ('/app-screen/challenge','/app-screen/authorize'):
   if not 1<=size<=1024:raise ValueError('size')
   raw=handler.rfile.read(size)
   if len(raw)!=size:raise ValueError('truncated')
   obj=json.loads(raw);keys=json.loads(config.read_text())
   if not isinstance(obj,dict):raise ValueError('body')
   if path.endswith('/challenge'):
    if set(obj)!={'device'}:raise ValueError('fields')
    result=AUTHORITY.challenge(obj['device'],keys)
   else:
    if set(obj)!={'device','challenge','proof'}:raise ValueError('fields')
    grant=AUTHORITY.authorize(obj['device'],obj['challenge'],obj['proof'],keys)
    result={'ticket':grant['ticket'],'expiresIn':grant['expiresIn'],'scope':'screen-frames'}
   handler.reply(200,json.dumps(result).encode());return True
  header=handler.headers.get('Authorization','')
  if not header.startswith('Bearer '):raise ValueError('auth')
  ticket=header[7:];device=subject(ticket)
  mailbox=CONVERSATION.mailbox
  if path.endswith('/stop'):
   if size!=0:raise ValueError('size')
   with AUTHORITY.lock:AUTHORITY.tickets.pop(ticket,None)
   with LOCK:SEQUENCES.pop(ticket,None)
   mailbox.cancel(device)
   handler.reply(200,b'{}');return True
  if handler.headers.get('Content-Type')!='image/jpeg' or not 1<=size<=524288:raise ValueError('size')
  sequence=int(handler.headers.get('X-Screen-Sequence','0'))
  if not 1<=sequence<=2147483647:raise ValueError('sequence')
  payload=handler.rfile.read(size)
  if len(payload)!=size:raise ValueError('truncated')
  with LOCK:
   for key in list(SEQUENCES):
    if key not in AUTHORITY.tickets:SEQUENCES.pop(key,None)
   if sequence<=SEQUENCES.get(ticket,0):raise ValueError('stale frame')
   SEQUENCES[ticket]=sequence
  with mailbox.lock:
   j=mailbox.jobs.get(device)
   if j is None or j.done or j.cancelled:
    handler.reply(202,b'{"accepted":false,"reason":"no active voice task"}');return True
   voice_session,voice_sequence,frame_sequence=j.session,j.sequence,j.video_sequence+1
  result=mailbox.ingest_video(device,voice_session,voice_sequence,frame_sequence,payload,'jpeg')
  result['source']='user-consented-app-screen'
  if frame_sequence==1 or frame_sequence%10==0:print('APP_SCREEN frame device=%s turn=%d frame=%d width=%d height=%d'%(device,voice_sequence,frame_sequence,result['width'],result['height']),flush=True)
  handler.reply(200,json.dumps(result).encode())
 except (ValueError,TypeError,KeyError,OSError):handler.reply(403,b'{"error":"screen session invalid or expired"}')
 return True
