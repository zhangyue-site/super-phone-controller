"""Device-authenticated voice facade for the existing ASR, chat queue and TTS.
No microphone background capture, phone grants, shell dispatch, or model fallback.
"""
import array,hashlib,hmac,io,json,math,os,re,subprocess,sys,tempfile,threading,time,wave
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
sys.path.insert(0,os.environ.get('COMPANION_PHONE_SERVER',str(Path(__file__).resolve().parents[1])))
from display_service import asr_plan,speech
ROOT=Path(os.environ['COMPANION_DATA'])
ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
class VoiceError(ValueError):pass

def lobster(request):
 runtime=os.environ.get('COMPANION_CHAT_RUNTIME')
 if not runtime:raise VoiceError('语音对话服务未配置')
 p=subprocess.run([sys.executable,runtime],input=json.dumps(request,ensure_ascii=False),capture_output=True,text=True,timeout=12)
 if p.returncode:raise VoiceError('龙虾连接未完成')
 o=json.loads(p.stdout)
 if o.get('status') not in (200,202):raise VoiceError('龙虾请求未接受，请稍后重试')
 return o['payload']

def asr(raw):
 a=array.array('h',raw)
 if math.sqrt(sum(x*x for x in a)/len(a))<80:raise VoiceError('声音太小，请靠近麦克风')
 fd,path=tempfile.mkstemp(suffix='.wav')
 try:
  with os.fdopen(fd,'wb') as f:
   with wave.open(f,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(raw)
  return asr_plan.transcribe(path)
 finally:os.unlink(path)

def usage(session,phase,provider,model,value):
 event={'session':session,'phase':phase,'provider':provider,'model':model,'usage':value,'at':time.time()}
 with open(ROOT/'usage.jsonl','a') as f:f.write(json.dumps(event,ensure_ascii=False)+'\n')

def tts(text,session):
 # Same subscription-only voice implementation as the existing server, with per-call accounting.
 import base64,urllib.request
 c=asr_plan.load_config();model='mimo-v2.5-tts'
 payload={'model':model,'messages':[{'role':'user','content':'请用清晰自然的普通话播报，语速略快。'},{'role':'assistant','content':text}], 'audio':{'format':'wav','voice':'mimo_default'}}
 req=urllib.request.Request(c['baseUrl'].rstrip('/')+'/chat/completions',json.dumps(payload).encode(),{'api-key':c['apiKey'],'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=35) as response:o=json.loads(response.read(4500000))
 usage(session,'tts','xiaomi-token-plan',model,o.get('usage'))
 return speech.pcm_from_wav(base64.b64decode(o['choices'][0]['message']['audio']['data'],validate=True))


def visible_text(value):
 return ''.join(c for c in str(value or '').strip() if c=='\n' or ord(c)>=32).encode()[:480].decode('utf-8','ignore')

def progress_detail(job,elapsed):
 label='等待首段回复'
 event_dir=os.environ.get('COMPANION_CHAT_EVENT_DIR')
 if event_dir and re.fullmatch(r'[0-9a-f-]{36}',job or ''):
  try:
   p=Path(event_dir)/('event-metadata-'+job+'.jsonl')
   with p.open('rb') as f:
    f.seek(0,2);size=f.tell();f.seek(max(0,size-64000));raw=f.read(64000)
   events=[]
   for line in raw.splitlines():
    try:e=json.loads(line)
    except (ValueError,UnicodeDecodeError):continue
    if e.get('run_matches') is True and e.get('agent_matches') is True and e.get('stream')=='tool':events.append(e)
   if events:label='正在查询资料' if events[-1].get('phase') in ('start','update') else '正在组织回答'
  except OSError:pass
 return label+' · '+str(int(elapsed))+'秒'

def voice_prompt(text):
 prompt='来自本人ESP32桌宠的语音对话。请自然简短地回答，最多140字，适合喇叭播报，不要Markdown。需要查资料时，先给一句简短的查询进度说明，再给结果。当前通道仅对话，不执行手机输入或发送、支付等外部动作；如需操作手机，提示通过现有手机控制入口确认。'
 if '天气' in text:prompt+='天气查询请优先使用已配置的天气工具；地点沿用已知用户位置，不明确时先询问。'
 return prompt+'用户说：'+text

class Turns:
 def __init__(self,asr_=asr,rpc=lobster,tts_=tts,clock=time.monotonic):
  self.asr=asr_;self.rpc=rpc;self.tts=tts_;self.clock=clock;self.lock=threading.RLock();self.turns={};self.seen={}
 def expire(self):
  with self.lock:
   for t in self.turns.values():
    if self.clock()-t['created']>=210 and t['state'] not in ('done','error','stopped'):
     t.update(stop=True,state='stopped',pcm=b'',detail='本轮语音已超时，不自动重试')
 def begin(self,device,session,raw,start=True):
  if not re.fullmatch('[0-9a-f]{16}',session) or not 12800<=len(raw)<=320000 or len(raw)%2:raise VoiceError('请录音0.4至10秒')
  self.expire()
  with self.lock:
   old=self.turns.get(device)
   if session in self.seen.get(device,set()):raise VoiceError('本次录音已提交，不重复执行')
   if old and old['state'] not in ('done','error','stopped'):raise VoiceError('上一轮语音仍在处理中')
   if len(self.turns)>=32 and device not in self.turns:raise VoiceError('语音服务暂忙')
   if len(self.seen.get(device,set()))>=2048:raise VoiceError('本次设备会话容量已满')
   self.seen.setdefault(device,set()).add(session)
   turn={'session':session,'state':'recognizing','recognizedText':'','reply':'','detail':'正在识别语音','pcm':b'','stop':False,'job':None,'owner':'esp32-companion:'+device,'created':self.clock()}
   self.turns[device]=turn
  if start:threading.Thread(target=self.run,args=(device,turn,raw),daemon=True).start()
  return self.status(device,session)
 def live(self,device,t):return self.turns.get(device) is t and not t['stop'] and self.clock()-t['created']<210
 def update(self,device,t,**values):
  with self.lock:
   if not self.live(device,t):return False
   t.update(values);return True
 def run(self,device,t,raw):
  try:
   result=self.asr(raw);raw=b''
   usage(t['session'],'asr',result.get('provider'),result.get('model'),result.get('usage'))
   text=result['text'].strip()[:120]
   if not text:raise VoiceError('没有识别到语音')
   if not self.update(device,t,recognizedText=text,state='queued',detail='语音已识别，正在等待回答'):return
   sessions=self.rpc({'op':'sessions','owner':t['owner']})['sessions']
   sid=sessions[0]['id'] if sessions else self.rpc({'op':'create','owner':t['owner'],'title':'ESP32 大肥鱼语音'})['session']['id']
   prompt=voice_prompt(text)
   if not self.live(device,t):return
   job=self.rpc({'op':'send','owner':t['owner'],'session_id':sid,'text':prompt,'idempotency_key':'esp32-voice-'+t['session']})['job']['id']
   with self.lock:t['job']=job
   if not self.live(device,t):self.rpc({'op':'cancel','owner':t['owner'],'job_id':job});return
   while self.live(device,t):
    j=self.rpc({'op':'job','owner':t['owner'],'job_id':job})['job']
    if j['status'] in ('queued','running'):
     partial=visible_text(j.get('partial_content',''))
     elapsed=self.clock()-t['created']
     detail='龙虾排队中 · '+str(int(elapsed))+'秒' if j['status']=='queued' else ('正在回复 · '+str(len(partial))+'字' if partial else progress_detail(job,elapsed))
     self.update(device,t,state='queued' if j['status']=='queued' else 'thinking',reply=partial,detail=detail)
     time.sleep(.4);continue
    if j['status']!='completed':raise VoiceError('龙虾本轮未完成，请重新说话')
    result=j.get('result') or {}
    usage(t['session'],'lobster','opencode-go',result.get('selected_model'),{'history_usage':result.get('history_usage'),'unavailable':result.get('history_usage_unavailable')})
    answer=j.get('partial_content','').strip()
    if not answer:
     msg=result.get('message',{});content=msg.get('content','') if isinstance(msg,dict) else ''
     answer=content if isinstance(content,str) else ''.join(x.get('text','') for x in content if x.get('type')=='text')
    answer=visible_text(answer)
    if not answer:raise VoiceError('龙虾没有返回可播报的文字')
    if not self.update(device,t,state='synthesizing',reply=answer,detail='龙虾已回答，正在合成语音'):return
    audio=self.tts(answer,t['session'])
    if not audio or len(audio)>960000 or len(audio)%2:raise VoiceError('语音播报数据未完成')
    self.update(device,t,state='ready',pcm=audio,detail='回答与语音已就绪');return
   self.rpc({'op':'cancel','owner':t['owner'],'job_id':job})
  except Exception as e:
   with self.lock:
    if self.live(device,t):t.update(state='error',detail=str(e)[:100] if isinstance(e,VoiceError) else '106语音链路暂不可用，请稍后重试',pcm=b'')
  finally:
   if t.get('job') and t['state'] not in ('ready','done'):
    try:self.rpc({'op':'cancel','owner':t['owner'],'job_id':t['job']})
    except Exception:pass
   with self.lock:
    if t['stop']:t.update(state='stopped',pcm=b'',detail='本轮已停止，迟到音频不播放')
 def get(self,device,session):
  t=self.turns.get(device)
  if not t or t['session']!=session:raise VoiceError('语音会话已失效')
  return t
 def status(self,device,session):
  self.expire()
  with self.lock:
   t=self.get(device,session)
   return {k:t[k] for k in ['session','state','recognizedText','reply','detail']}|{'sequence':1,'audioBytes':len(t['pcm'])}
 def audio(self,device,session):
  with self.lock:
   t=self.get(device,session)
   if t['stop'] or t['state']!='ready':raise VoiceError('语音未就绪或已停止')
   return t['pcm']
 def stop(self,device,session):
  with self.lock:
   t=self.get(device,session);t.update(stop=True,state='stopped',pcm=b'',detail='本轮已停止，迟到音频不播放');job=t['job'];owner=t['owner']
  if job:
   try:self.rpc({'op':'cancel','owner':owner,'job_id':job})
   except Exception:pass
  return self.status(device,session)
 def played(self,device,session):
  with self.lock:
   t=self.get(device,session)
   if not t['stop'] and t['state']=='ready':t.update(state='done',pcm=b'',detail='播报已结束')
  return self.status(device,session)

TURNS=Turns()
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def respond(self,code,value,kind='application/json'):
  raw=json.dumps(value,ensure_ascii=False).encode() if isinstance(value,dict) else value
  self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
 def device(self):
  config=json.loads(Path(os.environ['EPAPER_CONFIG']).read_text());auth=self.headers.get('Authorization','')
  for device,token in config.items():
   if hmac.compare_digest(auth,'Bearer '+token):return device
  return None
 def handle_request(self):
  self.connection.settimeout(8)
  try:
   device=self.device()
   if device is None:return self.respond(403,{'error':'device authorization required'})
   path=self.path;session=self.headers.get('X-Voice-Session','')
   if path=='/board-companion' and self.command=='GET':
    data=json.loads(Path(os.environ['EPAPER_REMOTE_STATE']).read_text());records=data.get('tasks',{})
    candidates=[(i,r) for i,r in records.items() if r.get('owner',[None]*4)[3]==device]
    active=[x for x in candidates if x[1].get('state') not in ('done','error','stopped','expired','replaced')]
    values=active or candidates
    if not values:return self.respond(200,{'state':'idle','verified':False,'terminal':True,'reply':'当前没有任务'})
    ident,r=values[-1];state=r.get('state','error');phase={'pending':'confirming','queued':'queued','done':'done','error':'error','stopped':'stopped'}.get(state,'unknown')
    return self.respond(200,{'task_id':ident,'state':state,'reply':r.get('reply','')[:160],'verified':r.get('verified') is True,'progress':{'phase':phase,'round':0,'completed':3 if state=='pending' else 7 if state=='queued' else 0}})
   if not re.fullmatch('[0-9a-f]{16}',session):raise VoiceError('语音会话无效')
   if self.command=='POST' and path=='/board-voice':
    size=int(self.headers.get('Content-Length','0'))
    if not 12800<=size<=320000 or size%2:raise VoiceError('录音长度无效')
    raw=self.rfile.read(size)
    if len(raw)!=size:raise VoiceError('录音上传未完成')
    return self.respond(202,TURNS.begin(device,session,raw))
   if self.command=='GET' and path=='/board-voice/status':return self.respond(200,TURNS.status(device,session))
   if self.command=='GET' and path=='/board-voice/audio':return self.respond(200,TURNS.audio(device,session),'application/octet-stream')
   if self.command=='POST' and path in ('/board-voice/stop','/board-voice/played'):
    if int(self.headers.get('Content-Length','0'))!=0:raise VoiceError('请求内容无效')
    return self.respond(200,(TURNS.stop if path.endswith('/stop') else TURNS.played)(device,session))
   return self.respond(404,{'error':'unknown endpoint'})
  except VoiceError as e:self.respond(409,{'error':str(e)})
  except (ValueError,KeyError,OSError,TypeError):self.respond(503,{'error':'voice service unavailable'})
 def do_GET(self):self.handle_request()
 def do_POST(self):self.handle_request()
class Server(ThreadingHTTPServer):
 def service_actions(self):TURNS.expire()

if __name__=='__main__':
 os.umask(0o077);Server(('127.0.0.1',int(os.environ.get('COMPANION_PORT','19059'))),Handler).serve_forever()
