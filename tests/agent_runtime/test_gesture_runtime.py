import copy,unittest
from types import SimpleNamespace as N
from unittest.mock import patch,Mock
from test_gesture_observation import raw,LINES,STEP,AUTH
from display_service import agent_runtime as r
from display_service.agent_observation import bind_visual
from display_service.agent_gesture_observation import geometry
from display_service.skill_engine import signature
from display_service.wechat_nav import WechatNavigator
from display_service.agent_gates import GateError
class Runtime(unittest.TestCase):
 def run_case(self,final_change=None,tamper=False,first_invalid=False,invalid_count=1):
  a=raw();b=raw([20,180,40,220]);final=raw(final_change) if final_change else b
  seq=[0];t=[1.];waited=[];sent=[];validated=[]
  def clock():t[0]+=.001;return t[0]
  def hint():return dict(width=200,height=400,source='phone-ocr',lines=copy.deepcopy(LINES),local_observation=dict(regions=[]))
  def fresh(*args,**kw):
   seq[0]+=1;data=a if seq[0]==1 else b;h=hint()
   if sent:
    data=raw([0,0,199,399]);h['lines']=[dict(row,text='changed'+str(i)) for i,row in enumerate(LINES)]
   return data,seq[0],signature(data),h
  info=dict(goal='翻页查看内容',scope=dict(source_app='内容页'),stages=[dict(id='page',goal='翻页',success='新页面')],completion=['已翻页'],questions=[],assumptions=[],capabilities=['observe','verify','page'],original='翻页查看内容')
  plans=[]
  def planner(data,h,inf,**kw):
   if kw.get('verify'):return dict(safe=True,done=True,step_verified=True,evidence='test new page',step=None)
   inf['_visual_evidence']=bind_visual(h,dict(scene='generic content',widgets=[],regions=[dict(role='scroll_container',bounds=STEP['bounds'])]))
   plans.append(1)
   step=copy.deepcopy(STEP)
   if first_invalid and len(plans)<=invalid_count:step['bounds']=[10,340,190,360]
   return dict(safe=True,done=False,evidence='test target',step=step)
  def wait(job,data,n,sig,h,bounds,label,**kw):waited.append(bounds);return data,n,sig,h
  nav=object.__new__(WechatNavigator);nav.m=N(_live=lambda job:None)
  nav._receipt_frame_floor=Mock(side_effect=lambda job,n:n);nav._frame=Mock(return_value=(final,99,signature(final)));nav._matches_action_frame=Mock(return_value=False)
  def action(guard,job,c,sig):
   if tamper:c["y2"]+=1
   data,n,current=guard._frame(job)
   valid=guard._matches_action_frame(sig,current,data);validated.append(valid)
   if not valid:raise GateError('final_frame_rejected','observation','reobserve','test final gate')
   sent.append(c);return {'ok':True}
  with patch.object(r,'fresh',side_effect=fresh),patch('display_service.agent_local_observation.wait_for_target',side_effect=wait),patch('display_service.phone_ocr.frame_hint',side_effect=lambda *args:hint()),patch.object(WechatNavigator,'_action',action):
   outcome=r.run(nav,N(device='device',screen_session='session',local_observation_capable=True),info['original'],authority=type(AUTH)(AUTH.goal_id,AUTH.device,AUTH.session,AUTH.lease,frozenset({'observe','verify','page','stop'}),AUTH.expires),guard=lambda _:True,policy=lambda *a:True,intake=lambda _:copy.deepcopy(info),planner=planner,clock=clock)
  return waited,sent,validated,outcome
 def test_runtime_wait_rebind_and_final_guard(self):
  waited,sent,validated,outcome=self.run_case()
  self.assertTrue(waited,outcome);self.assertEqual(waited[0],geometry(STEP,dict(width=200,height=400))[0]);self.assertEqual(len(sent),1,outcome);self.assertEqual(validated,[True]);self.assertTrue(outcome['verified'],outcome)
 def test_final_path_change_gets_no_input(self):
  waited,sent,validated,outcome=self.run_case([95,180,105,205]);self.assertTrue(waited,outcome);self.assertEqual(sent,[]);self.assertEqual(validated,[False])
 def test_final_hid_mutation_gets_no_input(self):
  waited,sent,validated,outcome=self.run_case(tamper=True);self.assertTrue(waited,outcome);self.assertEqual(sent,[]);self.assertEqual(validated,[False])
if __name__=='__main__':unittest.main()
