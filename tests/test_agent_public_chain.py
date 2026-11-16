"""Published Agent chain over the real HTTP handler, with a synthetic phone.

bridge prepare -> /remote/claim -> Conversation.start_remote -> agent_loader.run
-> agent_integration.run -> agent_runtime.run -> HID command -> fresh-frame check.
The planner is stubbed and the phone is simulated, so this locates which link
stops a task; it is not evidence of a real phone, model or board.
"""
import base64,hashlib,json,time
from unittest.mock import patch
import test_remote_http as fixture
from test_wechat_nav import frame
from display_service import accessibility,agent_intake,agent_local_observation,agent_runtime
TASK='打开设置'
UNDERSTANDING=dict(goal=TASK,scope=dict(source_app=None,target_app=None,start=None,end=None,dedup='',boundary=''),
 stages=[dict(id='s1',goal='进入设置',success='画面显示设置标题')],completion=['当前画面是设置'],questions=[],assumptions=[],capabilities=['open_app','tap_text','verify'])
LINES=(('相机','相册','设置','文件管理','音乐'),('设置','WLAN','蓝牙','显示与亮度','电池'))
AWAKE={'X-Screen-Interactive':'1','X-Screen-Keyguard-Locked':'0'}
LOCKED={'X-Screen-Interactive':'0','X-Screen-Keyguard-Locked':'1'}
def planner(payload):
 system=payload['messages'][0]['content'];user=payload['messages'][1]['content']
 if system.startswith('你是用户本人手机的通用任务理解器'):return dict(UNDERSTANDING)
 if system.startswith('你是手机识别链路Doctor'):return dict(summary='合成诊断',likely_causes=[],checks=[])
 data=json.loads(user[0]['text'] if isinstance(user,list) else user);seen=[row['text'] for row in data.get('ocr',[])]
 arrived='WLAN' in seen
 if data.get('verify'):return dict(safe=True,done=arrived,evidence='设置页面可见WLAN与蓝牙' if arrived else '仍在桌面',step=None,step_verified=arrived)
 if arrived:return dict(safe=True,done=True,evidence='设置页面可见WLAN与蓝牙',step=None)
 return dict(safe=True,done=False,evidence='桌面可见设置文字',step=dict(capability='tap_text',target='设置',locator='text',bounds=None))

class AgentPublicChain(fixture.RemoteHttpTests):
 # The legacy-navigator cases stay in their own module.
 test_both_origins_real_http_flow_and_scoped_verified_result=None
 test_bridge_auth_unknown_peer_cross_confirmation_and_stop=None
 test_remote_stop_blocks_voice_asr_already_in_flight=None
 def ocr(self,raw,stable):
  rows=[dict(text=text,bounds=[20+40*i,300,55+40*i,330] if self.stage==0 else [20,60+60*i,200,100+60*i]) for i,text in enumerate(LINES[min(self.stage,1)])]
  self.source+=1;now=self.source*100_000_000;regions=[]
  if self.requested:
   # A compliant phone counts consecutive unchanged source frames for the requested region.
   self.count=self.count+1 if stable else 1
   if self.count==1:self.first=now
   held=(now-self.first)//1_000_000
   regions=[dict(id=r['id'],label=r['label'],role='agent_target',bounds=r['bounds'],count=self.count,stableMs=held,ready=self.count>=10 and held>=600) for r in self.requested['regions']]
  local=dict(v=1,scopeHash='a'*64,sourceSequence=self.source,sourceTimestampNs=now,sourceWidth=240,sourceHeight=480,ageMs=10,requiredFrames=10,minStableMs=600,regions=regions,layoutHints=[])
  return dict(v=2,width=240,height=480,ageMs=10,sha256=hashlib.sha256(raw).hexdigest(),lines=rows,local=local)
 def drive(self,*,stable=True,static=False,screen=AWAKE):
  """Returns (final bridge status, HID ops, state dir, task id, stability requests seen by the phone)."""
  self.source=0;self.requested=None;self.count=0;self.first=0
  state=self.root/'state' # deliberately absent: a fresh deployment has no state root
  wait=agent_local_observation.wait_for_target
  with patch.dict('os.environ',{'EPAPER_PHONE_AGENT':'1','EPAPER_STATE':str(state)}),patch.object(agent_intake,'call_planner',planner),patch.object(agent_runtime,'call_planner',planner),patch.object(agent_runtime,'call_model',planner),patch.object(agent_local_observation,'wait_for_target',lambda *a,**k:wait(*a,**dict(k,budget=.3))):
   code,plan=self.bridge('prepare',self.tg,text=TASK);self.assertEqual((code,plan['state']),(200,'queued'));ident=plan['task_id']
   claim=self.request('/remote/claim',{'ready':True})[1]
   if claim['op']=='wait':claim=self.request('/remote/claim',{'ready':True})[1]
   self.assertEqual(claim,{'op':'start','task_id':ident})
   commands=[];requests=0;barrier='';number=0;pending=True;deadline=time.monotonic()+20
   while time.monotonic()<deadline:
    event=self.request('/dialogue/poll')[1];op=event.get('op')
    if op=='done':break
    if op not in ('wait',None):
     commands.append(op);self.assertEqual(op,'hid_pointer');self.stage+=1;pending=True
     self.assertEqual(self.request('/dialogue/result',{'id':event['id'],'ok':True,'output':'HID_POINTER_REPORT_SENT'})[0],200)
    code,status=self.request('/app-screen/status',None,'screen',screen);self.assertEqual(code,200)
    wanted=status.get('localObservationRequest')
    if wanted!=self.requested:
     self.requested=wanted;self.count=0;requests+=bool(wanted)
    if pending or not static:
     number+=1;raw=frame(min(self.stage,3))
     body=json.dumps(dict(jpegBase64=base64.b64encode(raw).decode(),ocr=self.ocr(raw,stable))).encode()
     code,reply=self.request('/app-screen/frame',body,'screen',{'Content-Type':accessibility.CONTENT_TYPE,'X-Screen-Sequence':str(number),'X-Screen-Barrier':barrier,'X-Screen-Native-Width':'240','X-Screen-Native-Height':'480'})
     self.assertIn(code,(200,202));barrier=reply.get('barrier',barrier)
     if code==200:pending=False
    if self.bridge('status',self.tg,task_id=ident)[1].get('terminal'):break
    time.sleep(.01)
   return self.bridge('status',self.tg,task_id=ident)[1],commands,state,ident,requests
 def test_fresh_deployment_and_compliant_phone_complete_one_verified_step(self):
  result,commands,state,ident,requests=self.drive()
  self.assertEqual((result['state'],result['verified']),('done',True),result['reply'])
  self.assertEqual(commands,['hid_pointer']);self.assertGreaterEqual(requests,1)
  saved=json.loads((state/'agent-runs'/(ident+'-result.json')).read_text())
  self.assertIsNone(saved['failure']);self.assertGreaterEqual(saved['local_stability'][-1]['count'],10)
 def test_unmet_stability_proof_never_sends_input_and_names_the_link(self):
  result,commands,state,ident,requests=self.drive(stable=False)
  self.assertEqual((result['state'],result['verified']),('error',False));self.assertEqual(commands,[])
  self.assertIn('未发送新的输入',result['reply']);self.assertIn('最近一轮：',result['reply'])
  saved=json.loads((state/'agent-runs'/(ident+'-result.json')).read_text())
  self.assertEqual(saved['failure']['code'],'observation_pipeline_blocked');self.assertEqual(requests,3)
  # The request reached the phone and came back on a frame every round: the
  # server links held, and the unmet proof is the phone's source-frame supply.
  self.assertEqual([row['request_region_observed'] for row in saved['local_stability_failures']],[True]*3)
 def still(self,screen,expected,code):
  result,commands,state,ident,_=self.drive(static=True,screen=screen)
  self.assertEqual((result['state'],commands),('error',[]))
  self.assertIn('共享授权仍有效',result['reply']);self.assertIn(expected,result['reply']);self.assertNotIn('请在App中共享',result['reply'])
  self.assertEqual(json.loads((state/'agent-doctor'/(ident+'.json')).read_text())['code'],code)
 def test_still_screen_reports_missing_frames_not_missing_share(self):self.still(AWAKE,'页面静止没有产生新画面','frame_unavailable')
 def test_locked_phone_state_reaches_the_reply_and_doctor(self):self.still(LOCKED,'手机已锁屏','screen_locked')
if __name__=='__main__':
 import unittest;unittest.main()
