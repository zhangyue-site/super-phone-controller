"""Android command capability: BLE proof, explicit confirmation, no long-lived key."""
import hashlib,json,os,re,threading
from .app_ota import Authority
from . import remote_http
from .paired_control import Pairings
AUTHORITY=Authority()
SESSION_LOCK=threading.RLock()
def authorize_target(obj,config):
 with SESSION_LOCK:
  grant=AUTHORITY.authorize(obj['device'],obj['challenge'],obj['proof'],json.loads(config.read_text()))
  with AUTHORITY.lock:
   for ticket,item in list(AUTHORITY.tickets.items()):
    if item[1]==obj['device'] and ticket!=grant['ticket']:AUTHORITY.tickets.pop(ticket,None)
  return grant
def renew_target(ticket,obj,config):
 with SESSION_LOCK:
  identity=owner(ticket)
  if obj['device']!=identity[3]:raise ValueError('fields')
  grant=AUTHORITY.authorize(obj['device'],obj['challenge'],obj['proof'],json.loads(config.read_text()))
  with AUTHORITY.lock:
   new=AUTHORITY.tickets.pop(grant['ticket'])
   old=AUTHORITY.tickets.get(ticket)
   if old is None or old[0]<=AUTHORITY.clock():raise PermissionError('expired')
   AUTHORITY.tickets[ticket]=new
  return {'expiresIn':grant['expiresIn'],'scope':'phone-commands'}
def renew_screen(target_ticket,screen_ticket):
 # Serialize target supersession, but never nest the two Authority locks or call
 # the mailbox: frame processing already uses screen authority -> mailbox.
 from . import app_screen
 with SESSION_LOCK:
  identity=owner(target_ticket)
  with AUTHORITY.lock:
   parent=AUTHORITY.tickets.get(target_ticket)
   if parent is None:raise PermissionError('expired')
   parent_deadline=parent[0]
  if not isinstance(screen_ticket,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',screen_ticket):raise PermissionError('screen')
  with app_screen.AUTHORITY.lock:
   now=app_screen.AUTHORITY.clock()
   app_screen.AUTHORITY._prune(now)
   item=app_screen.AUTHORITY.tickets.get(screen_ticket)
   if AUTHORITY.clock()>=parent_deadline or item is None or item[1]!=identity[3]:raise PermissionError('screen')
   app_screen.AUTHORITY.tickets[screen_ticket]=(now+300,*item[1:])
  return {'scope':'screen-frames','expiresIn':300}
def owner(ticket):
 if not isinstance(ticket,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',ticket):raise PermissionError('ticket')
 with AUTHORITY.lock:
  AUTHORITY._prune(AUTHORITY.clock());item=AUTHORITY.tickets.get(ticket)
  if item is None:raise PermissionError('expired')
  device=item[1]
 principal=hashlib.sha256(ticket.encode()).hexdigest()
 return ('android-app',principal,principal,device)
PAIRINGS=Pairings(lambda ticket:owner(ticket)[3])
def controller_owner(ticket):
 try:return owner(ticket)
 except PermissionError:return PAIRINGS.owner(ticket)
def bearer(handler):
 header=handler.headers.get('Authorization','')
 if not header.startswith('Bearer '):raise PermissionError('auth')
 return header[7:]
def binding_allowed(identity):
 # No authority lock is ever held while calling RemoteControl/mailbox.
 with AUTHORITY.lock:
  AUTHORITY._prune(AUTHORITY.clock())
  found=any(item[1]==identity[3] and hashlib.sha256(ticket.encode()).hexdigest()==identity[1]==identity[2] for ticket,item in AUTHORITY.tickets.items())
 return found or PAIRINGS.allowed(identity)
def handle(handler,config):
 path=handler.path
 if path not in ('/app-control/challenge','/app-control/authorize','/app-control/command','/app-control/renew','/app-control/pair-issue','/app-control/pair-redeem','/app-control/pair-renew','/app-control/pair-revoke','/app-control/screen-renew'):return False
 try:
  if handler.command!='POST':handler.reply(405,b'{}');return True
  if os.environ.get('EPAPER_REMOTE_CONTROL')!='1':handler.reply(503,b'{}');return True
  obj=remote_http.body(handler,2048)
  if path.endswith('/challenge'):
   if set(obj)!={'device'}:raise ValueError('fields')
   result=AUTHORITY.challenge(obj['device'],json.loads(config.read_text()))
  elif path.endswith('/authorize'):
   if set(obj)!={'device','challenge','proof'}:raise ValueError('fields')
   grant=authorize_target(obj,config)
   result={'ticket':grant['ticket'],'expiresIn':grant['expiresIn'],'scope':'phone-commands'}
  elif path.endswith('/screen-renew'):
   if set(obj)!={'ticket'}:raise ValueError('fields')
   result=renew_screen(bearer(handler),obj['ticket'])
  elif path.endswith('/renew'):
   if set(obj)!={'device','challenge','proof'}:raise ValueError('fields')
   result=renew_target(bearer(handler),obj,config)
  elif path.endswith('/pair-issue'):
   if obj:raise ValueError('fields')
   result=PAIRINGS.issue(bearer(handler))
  elif path.endswith('/pair-redeem'):
   if set(obj)!={'code'}:raise ValueError('fields')
   result=PAIRINGS.redeem(obj['code'])
  elif path.endswith('/pair-renew'):
   if obj:raise ValueError('fields')
   result=PAIRINGS.renew(bearer(handler))
  elif path.endswith('/pair-revoke'):
   if obj:raise ValueError('fields')
   device=PAIRINGS.revoke(bearer(handler))
   remote_http.REMOTE.stop_device(device)
   result={'state':'stopped','verified':False,'reply':'已撤销控制手机的连接并停止设备任务。'}
  else:
   header=handler.headers.get('Authorization','')
   if not header.startswith('Bearer '):raise PermissionError('auth')
   identity=controller_owner(header[7:])
   if set(obj)-{'operation','text','task_id'}:raise ValueError('fields')
   operation=obj.get('operation');remote=remote_http.REMOTE
   if operation=='prepare':
    result=remote.prepare(identity,obj.get('text'))
   elif operation=='confirm':
    ident=obj.get('task_id')
    if not isinstance(ident,str) or not re.fullmatch('[0-9a-f]{32}',ident):raise ValueError('请重新生成计划，再点击确认执行。')
    result=remote.confirm(identity,ident)
   elif operation=='status':result=remote.status(identity,obj.get('task_id'))
   elif operation=='stop':result=remote.stop(identity)
   elif operation=='save':result=remote.save(identity,obj.get('task_id'))
   else:raise ValueError('operation')
  if result.get('state')=='pending':result['reply']=result['reply'].split('回复 /phone 确认 ')[0]+'请在两分钟内点击“确认执行”。'
  handler.reply(200,json.dumps(result,ensure_ascii=False).encode())
 except PermissionError:handler.reply(403,json.dumps({'reply':'控制授权已失效，请重新连接授权。'},ensure_ascii=False).encode())
 except (ValueError,TypeError,KeyError) as error:
  message='授权未完成，请检查蓝牙连接后重试。' if not path.endswith('/command') else str(error)
  handler.reply(409,json.dumps({'reply':message},ensure_ascii=False).encode())
 except OSError:handler.reply(503,b'{}')
 return True
