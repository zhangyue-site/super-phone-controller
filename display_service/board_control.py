"""Device-authenticated BLE relay, bounded session ownership and replay suppression."""
import hashlib,json,re,threading,time
from collections import OrderedDict
from . import remote_http
HEX=re.compile(r'[0-9a-f]{32}\Z')
class Sessions:
 def __init__(self,clock=time.monotonic):
  self.clock=clock;self.lock=threading.RLock();self.devices={}
 def identity(self,device,session):return ('board-ble',session,session,device)
 def allowed(self,identity):
  state=self.devices.get(identity[3]);return bool(state and state['current']==identity[1]==identity[2])
 def dispatch(self,device,obj,remote):
  if set(obj)-{'session','request_id','operation','text','task_id','skill_id','parameters'}:raise ValueError('未知请求字段')
  session=obj.get('session');ident=obj.get('request_id');operation=obj.get('operation')
  if not isinstance(session,str) or not HEX.fullmatch(session) or not isinstance(ident,str) or not HEX.fullmatch(ident):raise ValueError('会话或请求ID无效')
  fields={'prepare':{'text'},'confirm':{'task_id'},'status':{'task_id'},'stop':set(),'save':{'task_id'},'skills':set(),'skill':{'skill_id','parameters'},'disconnect':set()}
  if operation not in fields or set(obj)-{'session','request_id','operation'}-fields[operation]:raise ValueError('操作或字段无效')
  digest=hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
  with self.lock:
   if device not in self.devices:
    if len(self.devices)>=256:raise ValueError('会话容量已满')
    self.devices[device]={'current':None,'retired':set(),'cache':OrderedDict(),'count':0}
   state=self.devices[device]
   if session in state['retired']:raise PermissionError('会话已失效')
   if operation=='disconnect' and session!=state['current']:
    # A delayed disconnect must never introduce an old nonce as the active owner.
    if len(state['retired'])>=1024:raise ValueError('会话次数已满，请重启控制服务')
    state['retired'].add(session)
    return {'state':'stopped','terminal':True,'verified':False,'reply':'旧蓝牙会话已注销，当前会话保持有效。'}

   if session!=state['current']:
    # Never forget retired nonces: reject further sessions at a bounded lifetime cap.
    if len(state['retired'])>=1024:raise ValueError('会话次数已满，请重启控制服务')
    old=state['current'];state['current']=session
    if old:
     state['retired'].add(old);remote.stop_device(device)
    state['cache'].clear();state['count']=0
   cached=state['cache'].get(ident)
   if cached:
    if cached[0]!=digest:raise ValueError('请求ID已用于其他内容')
    if cached[1] is None:raise ValueError('请求已消费，请查询状态')
    return cached[1]
   # IDs are never evicted while a nonce is active, so old actions cannot replay.
   if state['count']>=2048 and operation not in ('stop','disconnect'):raise ValueError('会话请求次数已满，请重新连接')
   state['count']+=1;state['cache'][ident]=(digest,None)
   owner=self.identity(device,session)
   if operation=='prepare':result=remote.prepare(owner,obj.get('text'))
   elif operation=='confirm':result=remote.confirm(owner,obj.get('task_id'))
   elif operation=='status':result=remote.status(owner,obj.get('task_id'))
   elif operation=='stop':
    result=remote.stop(owner)
    # Preserve consumed IDs, but never return an obsolete queued confirmation after STOP.
    for key,(old_digest,old_result) in list(state['cache'].items()):
     if old_result and old_result.get('task_id'):
      try:state['cache'][key]=(old_digest,remote.status(owner,old_result['task_id']))
      except ValueError:pass
   elif operation=='save':result=remote.save(owner,obj.get('task_id'))
   elif operation=='skills':result={'state':'skills','skills':remote.c.skills.cards(device),'terminal':True}
   elif operation=='skill':result=remote.prepare_skill(owner,obj.get('skill_id'),obj.get('parameters',{}))
   else:
    result=remote.stop(owner);state['retired'].add(session);state['current']=None
   if result.get('state')=='pending':result['reply']=result['reply'].split('回复 /phone 确认 ')[0]+'请在两分钟内点击“确认执行”。'
   if len(json.dumps(result,ensure_ascii=False).encode())>7800:
    result={'state':'rejected','error':'response_capacity','terminal':True,'reply':'技能或结果超过蓝牙响应容量，请减少已保存技能后重试。'}
   state['cache'][ident]=(digest,result)
   # STOP/disconnect must remain available under request floods without unbounded growth.
   if len(state['cache'])>2050:
    state['retired'].add(session);state['current']=None;state['cache'].clear()
   return result
SESSIONS=Sessions()
def handle(handler,config):
 if handler.path!='/board-control':return False
 try:
  if handler.command!='POST':handler.reply(405,b'{}');return True
  if __import__('os').environ.get('EPAPER_REMOTE_CONTROL')!='1':handler.reply(503,b'{}');return True
  device=handler.device()
  if device is None:raise PermissionError('设备授权失败')
  obj=remote_http.body(handler,2048)
  result=SESSIONS.dispatch(device,obj,remote_http.REMOTE)
  handler.reply(409 if result.get('error')=='response_capacity' else 200,json.dumps(result,ensure_ascii=False).encode())
 except PermissionError:handler.reply(403,json.dumps({'state':'rejected','reply':'设备授权或蓝牙会话已失效。'},ensure_ascii=False).encode())
 except (ValueError,TypeError,KeyError) as error:handler.reply(409,json.dumps({'state':'rejected','reply':str(error)},ensure_ascii=False).encode())
 except OSError:handler.reply(503,b'{"state":"unavailable"}')
 return True
