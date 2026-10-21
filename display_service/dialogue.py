"""Per-device turn mailbox. No cloud process gets an ADB socket or arbitrary shell."""
import json,re,threading,time,uuid,xml.etree.ElementTree as ET
from dataclasses import dataclass,field
DENY=re.compile(r'发送|支付|付款|转账|购买|充值|删除|清空|授权|权限|登录|退出|保存|提交|开启|关闭|修改|重置|卸载|安装|send|pay|buy|delete|remove|confirm|allow|permission|sign.?in|save|submit|install|reset',re.I)
NAV=re.compile(r'打开|进入|查看|返回|列表|详情|账单|设置|菜单|分类|首页|明细|记录|关于|帮助|搜索|home|settings|menu|details|list|back|help',re.I)

def parse_observation(raw):
 if not isinstance(raw,str) or len(raw.encode())>48000:raise ValueError('observation size')
 focus=re.search(r'^FOCUS ([A-Za-z0-9_.]+)/([^\s]+)',raw,re.M)
 size=re.search(r'^SIZE (\d+)x(\d+)',raw,re.M)
 if not focus or not size or not re.search(r'^LOCKED false$',raw,re.M):raise ValueError('phone locked or no foreground')
 if not re.search(r'^END_LOCKED false$',raw,re.M) or not re.search(r'^END_FOCUS '+re.escape(focus[1]+'/'+focus[2])+r'$',raw,re.M):raise ValueError('phone changed while observing')
 start=raw.find('<?xml');start=start if start>=0 else raw.find('<hierarchy');end=raw.rfind('</hierarchy>')
 if start<0 or end<0:raise ValueError('incomplete UI')
 root=ET.fromstring(raw[start:end+12]);nodes=[]
 for n in root.iter('node'):
  a=n.attrib
  if a.get('password')=='true':continue
  bounds=[int(v) for v in re.findall(r'\d+',a.get('bounds',''))]
  if len(bounds)!=4 or not 0<=bounds[0]<bounds[2]<=int(size[1]) or not 0<=bounds[1]<bounds[3]<=int(size[2]):continue
  if a.get('package') and a['package']!=focus[1]:raise ValueError('mixed foreground UI')
  label=' '.join((c.get('text','')+' '+c.get('content-desc','')).strip() for c in n.iter('node') if c.get('password')!='true')[:1000]
  if not label and a.get('clickable')!='true' and a.get('scrollable')!='true':continue
  nodes.append({'id':len(nodes),'label':label,'bounds':bounds,'clickable':a.get('clickable')=='true','scrollable':a.get('scrollable')=='true','enabled':a.get('enabled','true')=='true'})
 if not nodes:raise ValueError('no UI nodes')
 return {'package':focus[1],'activity':focus[2],'launcher':bool(re.search(r'^LAUNCHER '+re.escape(focus[1])+r'/',raw,re.M)),'nodes':nodes}

def action_command(d,obs):
 action=d.get('action')
 if action in ('home','back','open_settings'):return {'op':action}
 if action not in ('tap','scroll'):raise ValueError('unsupported action')
 i=d.get('node')
 if type(i)!=int or not 0<=i<len(obs['nodes']):raise ValueError('unknown node')
 n=obs['nodes'][i]
 if not n['enabled'] or not n['clickable' if action=='tap' else 'scrollable'] or DENY.search(n['label']):raise ValueError('node rejected')
 x1,y1,x2,y2=n['bounds'];x=(x1+x2)//2
 if action=='tap':
  if not NAV.search(n['label']):raise ValueError('only navigation controls allowed')
  return {'op':'tap','x':x,'y':(y1+y2)//2}
 direction=d.get('direction','up')
 if direction not in ('up','down'):raise ValueError('scroll direction')
 top=y1+(y2-y1)*3//10;bottom=y1+(y2-y1)*8//10
 return {'op':'swipe','x':x,'y':bottom if direction=='up' else top,'x2':x,'y2':top if direction=='up' else bottom}

def verify_done(task,d,obs):
 evidence=d.get('evidence')
 if not isinstance(evidence,str) or not evidence.strip() or not any(evidence in n['label'] for n in obs['nodes']):return False
 if '打开' in task and obs['launcher']:return False
 if re.search(r'打开.*设置',task) and obs['package']!='com.android.settings':return False
 if re.search(r'(回到|返回|回).*桌面|手机首页',task) and not obs['launcher']:return False
 return True

@dataclass
class Job:
 device:str
 session:str
 sequence:int
 created:float
 touched:float
 cancelled:bool=False
 command:dict|None=None
 delivered:bool=False
 result:tuple|None=None
 audio:bytes=b''
 reply:str=''
 speech_error:bool=False
 state:str='thinking'
 done:bool=False
 event:threading.Event=field(default_factory=threading.Event)

class Mailbox:
 def __init__(self,clock=time.monotonic):self.clock=clock;self.lock=threading.RLock();self.jobs={};self.high={}
 def _live(self,j):
  if j.cancelled or self.clock()-j.created>180 or self.clock()-j.touched>15:
   j.cancelled=True;j.event.set();raise ValueError('turn cancelled or expired')
 def _job(self,device,session,seq):
  j=self.jobs.get(device)
  if not j or (j.session,j.sequence)!=(session,seq):raise ValueError('unknown turn')
  self._live(j);return j
 def create(self,device,session,seq):
  with self.lock:
   key=(device,session)
   if seq<=self.high.get(key,0):raise ValueError('duplicate turn')
   old=self.jobs.get(device)
   if old and not old.done and not old.cancelled and self.clock()-old.touched<=15:raise ValueError('turn busy')
   if old:old.cancelled=True;old.event.set()
   self.high[key]=seq
   if len(self.high)>256:self.high.pop(next(iter(self.high)))
   now=self.clock();j=Job(device,session,seq,now,now);self.jobs[device]=j;return j
 def offer(self,j,command):
  with self.lock:
   self._live(j)
   if j.command:raise ValueError('command busy')
   j.result=None;j.delivered=False;j.command=dict(command,id=uuid.uuid4().hex);j.event.clear()
 def poll(self,device,session,seq):
  with self.lock:
   j=self._job(device,session,seq);j.touched=self.clock()
   if j.command and not j.delivered:j.delivered=True;return dict(j.command)
   return {'op':'done' if j.done else 'wait','state':j.state,'reply':j.reply,'audio':bool(j.audio),'speechError':j.speech_error}
 def ack(self,device,session,seq,ident,ok,output):
  with self.lock:
   j=self._job(device,session,seq)
   if not j.command or not j.delivered or ident!=j.command['id']:raise ValueError('stale acknowledgement')
   j.result=(ok,output);j.command=None;j.touched=self.clock();j.event.set()
 def execute(self,j,command):
  self.offer(j,command)
  until=self.clock()+35
  while self.clock()<until:
   j.event.wait(.2)
   with self.lock:
    self._live(j)
    if j.result is not None:
     ok,out=j.result;j.result=None
     if not ok:raise ValueError('phone command failed; not retried')
     return out
  raise TimeoutError('phone acknowledgement timeout; not retried')
 def cancel(self,device,session=None,sequence=None):
  with self.lock:
   j=self.jobs.get(device)
   if j and (session is None or (j.session==session and j.sequence<=sequence)):
    j.cancelled=True;j.audio=b'';j.event.set()
 def audio(self,device,session,seq):
  with self.lock:return self._job(device,session,seq).audio
