import io,unittest,copy
from PIL import Image
from types import SimpleNamespace as N
from unittest.mock import Mock,patch
from display_service import agent_runtime as r
from display_service.agent_contract import Authority
from display_service.agent_local_observation import TargetNotStable
from display_service.skill_engine import signature
class RuntimeBound(unittest.TestCase):
 def test_third_source_failure_stops_without_any_hid_input(self):
  out=io.BytesIO();Image.new("RGB",(200,400),"white").save(out,format="JPEG");raw=out.getvalue();seq=[0];t=[1.]
  def clock():t[0]+=.001;return t[0]
  def fresh(*a,**kw):
   seq[0]+=1
   return raw,seq[0],signature(raw),dict(width=200,height=400,source="phone-ocr",lines=[dict(text=x,bounds=[10,50+i*30,100,70+i*30])for i,x in enumerate(["状态","网络","时间","电量"])])
  info=dict(goal="打开控制中心",scope={},stages=[dict(id="open",goal="打开",success="面板")],completion=["控制中心"],questions=[],assumptions=[],capabilities=["observe","verify"],original="打开控制中心")
  auth=Authority("t","d","s","lease",frozenset({"observe","verify","edge_swipe","stop"}),999.)
  action=Mock(side_effect=AssertionError("stability failure cannot send input"))
  def planner(*a,**kw):return dict(safe=True,done=False,evidence="准备观察面板",step=dict(capability="edge_swipe",target="控制中心",locator="edge",bounds=None,edge="top",anchor_percent=85,distance_percent=60))
  with patch.object(r,"fresh",side_effect=fresh),patch("display_service.agent_local_observation.wait_for_target",side_effect=TargetNotStable("no fresh source frames"))as wait:
   result=r.run(N(m=N(_live=lambda j:None),_action=action),N(device="d",screen_session="s",local_observation_capable=True,video_barrier="a"*32),info["original"],authority=auth,guard=lambda a:True,policy=lambda *a:True,intake=lambda _:copy.deepcopy(info),planner=planner,clock=clock)
  self.assertEqual(wait.call_count,3);self.assertFalse(result["verified"]);self.assertEqual(result["failure"]["code"],"observation_pipeline_blocked");action.assert_not_called()
if __name__=="__main__":unittest.main()
