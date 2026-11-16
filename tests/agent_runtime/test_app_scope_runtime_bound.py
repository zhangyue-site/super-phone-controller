import io,unittest,copy
from PIL import Image
from types import SimpleNamespace as N
from unittest.mock import Mock,patch
from display_service import agent_runtime as r
from display_service.agent_contract import Authority
from display_service.skill_engine import signature
class ScopeRuntime(unittest.TestCase):
 def test_third_wrong_app_candidate_stops_without_hid(self):
  out=io.BytesIO();Image.new("RGB",(200,400),"white").save(out,format="JPEG");raw=out.getvalue();seq=[0];t=[1.];plans=[]
  def clock():t[0]+=.001;return t[0]
  def fresh(*a,**kw):
   seq[0]+=1
   return raw,seq[0],signature(raw),dict(width=200,height=400,source="phone-ocr",lines=[dict(text="谷歌",bounds=[10,50,100,70])])
  info=dict(goal="打开浏览器",scope=dict(source_app="浏览器"),stages=[dict(id="open",goal="打开",success="浏览器")],completion=["浏览器"],questions=[],assumptions=[],capabilities=["observe","verify"],original="打开浏览器")
  auth=Authority("t","d","s","lease",frozenset({"observe","verify","open_app","stop"}),999.)
  action=Mock(side_effect=AssertionError("wrong application must not get HID input"))
  def planner(*a,**kw):
   plans.append(1)
   return dict(safe=True,done=False,evidence="错误候选",step=dict(capability="open_app",target="谷歌",locator="text",bounds=[10,50,100,70]))
  with patch.object(r,"fresh",side_effect=fresh):
   result=r.run(N(m=N(_live=lambda j:None),_action=action),N(device="d",screen_session="s"),info["original"],authority=auth,guard=lambda a:True,policy=lambda *a:True,intake=lambda _:copy.deepcopy(info),planner=planner,clock=clock)
  self.assertEqual(len(plans),3);self.assertEqual(result["failure"]["code"],"planner_scope_blocked");self.assertFalse(result["verified"]);action.assert_not_called()
