"""Owner-confirmed text plans; bridge never exposes device credentials or shell."""
import json,os,re,threading,time,uuid
from pathlib import Path
from .wechat_nav import parse_task
from .general_nav import parse_task as parse_general
TERMINAL=frozenset(('done','error','stopped','expired','replaced'))
CHANNELS=frozenset(('openclaw-weixin','telegram','android-app'))
class RemoteControl:
 def __init__(self,conversation,path=None,clock=time.monotonic,screen_ready=None):
  self.c=conversation;self.path=Path(path or os.environ.get('EPAPER_REMOTE_STATE','/var/lib/phone-controller/remote-control.json'));self.clock=clock
  self.screen_ready=screen_ready or (lambda _:False);self.lock=threading.RLock();self.records={};self.jobs={};self.board_turns={};self.boots={};self.pending_boots={}
  self.runtime_lock=threading.RLock();self.voice_busy=lambda _:False;self.cancel_voice=lambda _:None;self.turn_allowed=lambda *a:True;self.binding_allowed=lambda _:True
  try:
   if self.path.stat().st_size>1000000:raise ValueError('state size')
   records=json.loads(self.path.read_text())['tasks']
   if not isinstance(records,dict):raise ValueError('state')
   for ident,r in records.items():
    if not re.fullmatch('[0-9a-f]{32}',ident) or not isinstance(r,dict):continue
    if r.get('state') not in TERMINAL:r.update(state='error',reply='服务已重启，旧任务已取消；请重新发起并确认。',verified=False)
    self.records[ident]=r
  except FileNotFoundError:pass
 def _save(self):
  from .cloud_progress import utc_now
  for r in self.records.values():
   signature=[r.get('state'),r.get('reply'),r.get('verified')]
   if r.get('_public_signature')!=signature:r['_public_signature']=signature;r['updated_at']=utc_now()
  self.path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
  tmp=self.path.with_suffix('.tmp');raw=json.dumps({'schema':1,'tasks':self.records},ensure_ascii=False)
  with tmp.open('w') as f:os.chmod(tmp,0o600);f.write(raw);f.flush();os.fsync(f.fileno())
  os.replace(tmp,self.path)
 def _owner(self,owner):
  if not isinstance(owner,(tuple,list)) or len(owner)!=4 or owner[0] not in CHANNELS or any(not isinstance(v,str) or not 1<=len(v)<=256 for v in owner):raise ValueError('入口身份无效')
  if not re.fullmatch('[A-Za-z0-9_-]{1,64}',owner[3]):raise ValueError('设备无效')
  return list(owner)
 def _get(self,owner,ident=None):
  owner=self._owner(owner)
  if ident is None:
   options=[(i,r) for i,r in self.records.items() if r['owner']==owner]
   if not options:raise ValueError('当前会话还没有手机任务')
   return options[-1]
  r=self.records.get(ident)
  if not r or r['owner']!=owner:raise ValueError('任务不属于当前会话')
  return ident,r
 def _sync(self):
  changed=False;now=self.clock()
  for ident,r in self.records.items():
   before=(r.get('state'),r.get('reply'),r.get('verified'));j=self.jobs.get(ident)
   if r['state'] not in TERMINAL and not self.binding_allowed(r['owner']):
    if j:self.c.mailbox.cancel(r['owner'][3],r.get('session'),r.get('sequence'))
    r.update(state='error',reply='当前入口授权已撤销，本次任务已取消。',verified=False)
   elif r['state']=='pending' and now>=r['expires']:r.update(state='expired',reply='确认已超时，请重新发起。')
   elif r['state']=='queued' and r.get('expires') is not None and now>=r['expires']:r.update(state='expired',reply='领取已超时，请重新发起。',verified=False)
   elif r['state']=='running':
    if j is None:r.update(state='error',reply='任务连接丢失，请重新发起。',verified=False)
    elif j.cancelled:r.update(state='stopped',reply='后续动作已撤销，设备停止待确认。',verified=False)
    elif j.done:
     verified=bool(j.navigation_verified and j.state=='done')
     r.update(state='done' if verified else 'error',reply=j.reply or '操作未完成核验。',verified=verified)
    elif now-r['claimed']>(j.max_age+5 if getattr(j,'agent_job',False) else 185):
     self.c.mailbox.cancel(r['owner'][3],r['session'],r['sequence']);r.update(state='error',reply='执行超时，任务已取消。',verified=False)
   changed=changed or before!=(r.get('state'),r.get('reply'),r.get('verified'))
  if changed:self._save()
 def _reply(self,ident,r):
  from .cloud_progress import summary,utc_now
  return dict(task_id=ident,state=r['state'],reply=r['reply'],verified=bool(r.get('verified')),terminal=r['state'] in TERMINAL,serverCancelled=r['state']=='stopped',stopConfirmed=False,cloudTask=summary(ident,r['owner'][0],r['state'],bool(r.get('verified')),r.get('updated_at')),observedAt=utc_now())
 def prepare(self,owner,text):
  owner=self._owner(owner)
  agent=os.environ.get('EPAPER_PHONE_AGENT')=='1'
  if not isinstance(text,str) or not text.strip() or len(text)>(2000 if agent else 120) or (not agent and parse_task(text) is None and parse_general(text) is None):raise ValueError('任务原文无效或当前入口不支持。')
  query=parse_task(text)
  with self.lock:
   self._sync()
   for r in self.records.values():
    if r['owner']==owner and r['state']=='pending':r.update(state='replaced',reply='已有新指令，旧确认已失效。')
   if len(self.records)>=128:
    for ident in list(self.records):
     if self.records[ident]['state'] in TERMINAL:self.records.pop(ident);self.jobs.pop(ident,None);break
    else:raise ValueError('待处理任务过多')
   ident=uuid.uuid4().hex;reply='计划：从桌面打开微信，搜索'+(query or '')+'，停在搜索结果页，不发消息。回复 /phone 确认 '+ident+' 后执行；两分钟内有效。'
   if query is None:reply='计划：'+text+'；仅执行安全导航，保留结果页并独立核验。确认 '+ident+' 后执行；两分钟有效。'
   if agent:reply='目标：'+text+'。将检查现场并制订计划，再执行已具备的技能和核验结果；具体步骤尚未生成，请确认目标。'
   r=dict(owner=owner,text=text,state='pending',reply=reply,expires=self.clock()+120,verified=False)
   self.records[ident]=r;self._save();return self._reply(ident,r)
 def confirm(self,owner,ident):
  with self.lock,self.runtime_lock,self.c.mailbox.lock:
   self._sync();ident,r=self._get(owner,ident)
   if r['state'] in ('queued','running','done'):return self._reply(ident,r)
   if r['state']!='pending':raise ValueError('该确认已失效，请重新发起任务')
   device=r['owner'][3]
   if any(v is not r and v['owner'][3]==device and v['state'] in ('queued','running') for v in self.records.values()):raise ValueError('控制板正在处理另一任务，请稍后再确认')
   if self.voice_busy(device):raise ValueError('语音仍在处理中，请先停止或等待完成')
   j=self.c.mailbox.jobs.get(device)
   if j and not j.done and not j.cancelled:raise ValueError('控制板正在处理语音任务，请先停止或等待完成')
   r.update(state='queued',expires=self.clock()+60,reply='已进入队列，会等到控制板领取；请保持手机解锁、整屏共享和板端HID许可。');self._save();return self._reply(ident,r)
 def claim(self,device,session,sequence,ready,pointer_protocol,lease=None):
  if not isinstance(session,str) or not re.fullmatch('[0-9a-f]{16}',session) or type(sequence)!=int or not 1<=sequence<=2147483647:raise ValueError('turn')
  # Snapshot consent before mailbox lock: screen handlers lock AUTHORITY then mailbox.
  has_screen=self.screen_ready(device)
  with self.lock,self.runtime_lock,self.c.mailbox.lock:
   self._sync()
   boot=self.boots.get(device)
   if boot is None or boot['session']!=session:
    if boot and session in boot['retired']:return {'op':'wait'}
    key=(device,session);pending=self.pending_boots.get(key)
    if not pending or self.clock()-pending[1]>30 or lease!=pending[0]:
     if not pending or self.clock()-pending[1]>30:
      pending=(uuid.uuid4().hex+uuid.uuid4().hex,self.clock());self.pending_boots[key]=pending
     return {'op':'wait','lease':pending[0]}
    retired=(boot['retired']+[boot['session']])[-16:] if boot else []
    boot={'session':session,'lease':lease,'high':0,'retired':retired};self.boots[device]=boot
    self.pending_boots={k:v for k,v in self.pending_boots.items() if k[0]!=device}
   if lease!=boot['lease']:return {'op':'wait','lease':boot['lease']}
   if sequence<=boot['high'] or not self.turn_allowed(device,session,sequence):print('CLAIM wait: fence',sequence,boot['high'],flush=True);return {'op':'wait'}
   boot['high']=sequence;self.board_turns[device]=(session,sequence)
   if self.voice_busy(device):print('CLAIM wait: voice_busy',flush=True);return {'op':'wait'}
   # 2026-11-11 autoclaim: bound private-chat tasks self-establish the screen session (user approved); drop has_screen precondition
   if ready is not True or pointer_protocol!='absolute-v1':print('CLAIM wait: ready/pointer',ready,pointer_protocol,flush=True);return {'op':'wait'}
   existing=self.c.mailbox.jobs.get(device)
   if existing and not existing.done and not existing.cancelled:print('CLAIM wait: mailbox_busy',flush=True);return {'op':'wait'}
   for ident,r in self.records.items():
    if r['owner'][3]!=device or r['state']!='queued':continue
    # Android pairing never substitutes for current explicit screen consent.
    if r['owner'][0]=='android-app' and not has_screen:return {'op':'wait'}
    # Persist consumption before execution; a lost reply never causes replay.
    r.update(state='running',session=session,sequence=sequence,claimed=self.clock(),screen_seen=bool(has_screen),screen_wait_until=self.clock()+15,reply='控制板已领取，正在观察手机画面。' if has_screen else '控制板已领取，等待手机建立本次共享；等待期间不执行输入。');self._save()
    try:
     if hasattr(self.c,'start_remote'):j=self.c.start_remote(device,session,sequence,r['text'],ident,pointer_protocol,lease)
     else:j=self.c.start(device,session,sequence,r['text'])
     self.jobs[ident]=j
     j.remote_task_id=ident;j.pointer_protocol=pointer_protocol
    except Exception:
     r.update(state='error',reply='控制板领取失败，任务未重试。');self._save();raise
    print('CLAIM START',ident,flush=True);return {'op':'start','task_id':ident}
   return {'op':'wait'}
 def board_status(self,device,session,sequence):
  # Capture authority is sampled before mailbox/remote locks, matching claim.
  has_screen=self.screen_ready(device)
  with self.lock:
   self._sync()
   for ident,r in self.records.items():
    if r['owner'][3]==device and (r.get('session'),r.get('sequence'))==(session,sequence):
     if r['state']=='running':
      if has_screen:
       if not r.get('screen_seen',True):
        r.update(screen_seen=True,reply='控制板已领取，正在观察手机画面。');self._save()
      elif not r.get('screen_seen',True) and self.clock()<r.get('screen_wait_until',r['claimed']):
       return {'op':'wait','waiting_for_screen':True}
      else:
       self.c.mailbox.cancel(device,session,sequence)
       message='屏幕共享授权已结束，本次任务已取消。' if r.get('screen_seen',True) else '等待本次屏幕共享超时，本次任务已取消；未重放输入。'
       r.update(state='error',reply=message,verified=False);self._save()
     return {'op':'wait' if r['state']=='running' else 'done' if r['state']=='done' else 'cancelled'}
   return {'op':'cancelled'}
 def status(self,owner,ident=None):
  with self.lock:
   self._sync();owner=self._owner(owner)
   if ident is None and not any(r['owner']==owner for r in self.records.values()):
    return dict(state='idle',reply='当前没有手机控制任务。发送 /phone 打开微信找到李洋 可先查看计划。',terminal=True,verified=False)
   ident,r=self._get(owner,ident);out=self._reply(ident,r)
   if r['state']=='queued':
    from . import events
    code=events.latest_exec(r['owner'][3])
    labels={0:'板端心跳：可以执行。',1:'板端心跳：未插入USB。',2:'板端心跳：未连上服务器。',3:'板端心跳：键鼠未开启。',4:'板端心跳：上一次任务失败。'}
    out['reply']=out['reply']+' '+(labels[code] if code in labels else '还没有板端心跳。')
   return out
 def public_device_status(self,device):
  from .cloud_progress import summary
  with self.lock:
   self._sync()
   found=[(ident,r) for ident,r in self.records.items() if r['owner'][3]==device]
   if not found:return None
   mailbox_id=getattr(self.c.mailbox.jobs.get(device),'remote_task_id',None)
   ranked=[(ident,r) for ident,r in found if ident==mailbox_id and r['state']=='running']
   if not ranked:
    for state in ('running','queued','pending'):
     ranked=[(ident,r) for ident,r in found if r['state']==state]
     if ranked:break
   ident,r=(ranked or found)[-1]
   return summary(ident,r['owner'][0],r['state'],bool(r.get('verified')),r.get('updated_at'))
 def stop_device(self,device):
  with self.lock,self.runtime_lock:
   self._sync();self.cancel_voice(device)
   for ident,r in self.records.items():
    if r['owner'][3]==device and r['state'] not in TERMINAL:r.update(state='stopped',reply='后续动作已撤销，设备停止待确认。',verified=False)
   self.c.mailbox.cancel(device);self.c.skills.invalidate(device) if hasattr(self.c,'skills') else None;self._save()
 def stop_board(self,device,session,sequence):
  with self.lock:
   seen=self.board_turns.get(device)
   if seen is not None and seen[0]==session and sequence>=seen[1]:
    self.stop_device(device);return
   retired=self.boots.get(device,{}).get('retired',[])
   if session not in retired and (seen is None or seen[0]!=session or (device,session) in self.pending_boots):
    changed=False
    for r in self.records.values():
     if r['owner'][3]==device and r['state'] in ('pending','queued'):
      r.update(state='stopped',reply='板端已停止，待执行计划已取消。',verified=False);changed=True
    if changed:self._save()
 def stop(self,owner):
  owner=self._owner(owner);self.stop_device(owner[3]);return dict(state='stopped',terminal=True,reply='后续动作已撤销并请求停止；设备停止尚未确认。',verified=False,serverCancelled=True,stopConfirmed=False)
 def save(self,owner,ident=None):
  with self.lock:
   self._sync();ident,r=self._get(owner,ident)
   if r['state']!='done' or not r.get('verified'):raise ValueError('只有当前会话核验成功的任务可以存为技能')
   j=self.jobs.get(ident)
   if j is None or self.c.mailbox.jobs.get(owner[3]) is not j:raise ValueError('最近任务已经变化，请重新核验后保存')
   name=self.c.skills.save_last(owner[3]);return dict(task_id=ident,state='saved',terminal=True,reply='已存为技能：'+name,verified=True)
