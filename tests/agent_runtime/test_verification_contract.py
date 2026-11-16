import unittest,io,json
from PIL import Image
from display_service.agent_runtime import observe_plan
from display_service.agent_contract import Authority
from display_service.agent_observation import capture
class Verification(unittest.TestCase):
 def setup(self):
  out=io.BytesIO();Image.new('RGB',(200,400),'white').save(out,format='JPEG');raw=out.getvalue();auth=Authority('t','d','s','lease',frozenset(['observe','edge_swipe','verify']),999.)
  hint=capture(auth,1,raw,dict(width=200,height=400,lines=[dict(text='中国移动',bounds=[10,30,100,50]),dict(text='播放',bounds=[20,150,80,170]),dict(text='无线网络',bounds=[20,80,110,100])]),observed_at=1.).hint()
  info=dict(original='请打开系统设置',goal='系统设置首页',scope={},stages=[],completion=['设置首页'],_platform='android',_last_action=dict(capability='edge_swipe',target='打开控制中心',receipt='confirmed'))
  return raw,hint,info
 def test_invalid_verification_is_corrected_read_only_once_with_current_visual(self):
  raw,hint,info=self.setup();calls=[];visions=[]
  def model(payload):
   calls.append(payload)
   request=json.loads(payload["messages"][1]["content"][0]["text"]);self.assertNotIn("tool_manifest",request);self.assertNotIn("preset_catalog",request)
   if len(calls)==1:return dict(safe=True,done=False,evidence='还未到设置',step=dict(capability='edge_swipe',target='再下拉'))
   return dict(safe=True,done=False,step_verified=True,evidence='当前控制中心已展开，但设置目标未完成',step=None)
  def vision(payload):visions.append(payload);return dict(scene='系统控制中心',widgets=[],regions=[])
  result=observe_plan(raw,hint,info,verify=True,model=model,vision_model=vision)
  self.assertIs(result.get('step_verified'),True);self.assertIsNone(result['step']);self.assertFalse(result['done']);self.assertEqual(len(calls),2);self.assertEqual(len(visions),1)
 def test_repeated_invalid_contract_stops_instead_of_coercing_or_replaying(self):
  raw,hint,info=self.setup();calls=[]
  def model(payload):calls.append(payload);return dict(safe=True,done=False,evidence='再下拉',step=dict(capability='edge_swipe'))
  with self.assertRaises(ValueError):observe_plan(raw,hint,info,verify=True,model=model,vision_model=lambda p:dict(scene='当前系统面板',widgets=[],regions=[]))
  self.assertEqual(len(calls),2)
 def test_explicit_false_is_preserved(self):
  raw,hint,info=self.setup();result=observe_plan(raw,hint,info,verify=True,model=lambda p:dict(safe=True,done=False,step_verified=False,evidence='尚不能确认面板',step=None),vision_model=lambda p:dict(scene='unknown',widgets=[],regions=[]));self.assertIs(result['step_verified'],False)
if __name__=='__main__':unittest.main()
