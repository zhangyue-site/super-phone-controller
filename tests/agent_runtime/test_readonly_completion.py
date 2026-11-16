import unittest,io
from PIL import Image
from types import SimpleNamespace as N
from unittest.mock import Mock,patch
from display_service import agent_runtime as r
from display_service.agent_contract import Authority
from display_service.skill_engine import signature
class ReadonlyCompletion(unittest.TestCase):
 def test_null_step_checks_next_frame_without_phone_input(self):
  out=io.BytesIO();Image.new("RGB",(200,400),"white").save(out,format="JPEG");raw=out.getvalue();seq=[0];t=[1.];calls=[]
  def clock():t[0]+=.001;return t[0]
  def fresh(*a,**kw):
   seq[0]+=1
   return raw,seq[0],signature(raw),dict(width=200,height=400,source="phone-ocr",lines=[dict(text="设置",bounds=[10,30,80,50])])
  info=dict(goal="观察设置页面",scope={},stages=[dict(id="view",goal="观察",success="设置可见")],completion=["设置可见"],questions=[],assumptions=[],capabilities=["observe","verify"],original="请观察当前设置页面")
  info["_action_before_image"]=dict(jpeg=b"private-original-frame",observation={})
  def plan(raw,hint,info,verify=False):
   calls.append((verify,hint["_observation"]["frame_id"]))
   return dict(safe=True,done=verify,step_verified=verify,evidence="设置可见，需只读核验" if not verify else "新帧确认设置可见",step=None)
  action=Mock(side_effect=AssertionError("readonly completion must never inject input"))
  with patch.object(r,"fresh",side_effect=fresh):
   result=r.run(N(m=N(_live=lambda j:None),_action=action),N(device="d",screen_session="s"),info["original"],authority=Authority("t","d","s","lease",frozenset(info["capabilities"]),999.),guard=lambda a:True,policy=lambda *a:True,intake=lambda t:info,planner=plan,clock=clock)
  import json
  json.dumps(result)
  self.assertNotIn("_action_before_image",result["understanding"])
  self.assertTrue(result["verified"],result);self.assertEqual([x[0]for x in calls],[False,True]);self.assertNotEqual(calls[0][1],calls[1][1]);action.assert_not_called()
