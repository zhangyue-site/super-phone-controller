import unittest,json
from unittest.mock import patch
from display_service import agent_runtime as r
import test_verify_contract as fixtures
class HomeArrival(unittest.TestCase):
 def test_verified_home_refreshes_actual_scene_before_next_planning(self):
  hint,info=fixtures.VerificationContract().fixtures("home")
  info["_navigation"]=[dict(action=dict(capability="home"),step_verified=True,observed="桌面可见")]
  seen=[]
  def image(payload):
   seen.append(payload)
   return dict(scene="Android桌面",widgets=[dict(label="浏览器",role="app_icon",bounds=[180,1100,275,1200])],regions=[])
  def model(payload):
   data=json.loads(payload["messages"][1]["content"][0]["text"])
   if data.get("visual_observation",{}).get("scene")=="Android桌面":
    return dict(safe=True,done=False,evidence="当前独立画面为桌面，应打开浏览器",step=dict(capability="open_app",target="浏览器",locator="icon",bounds=[180,1100,275,1200]))
   return dict(safe=True,done=False,evidence="误把历史美团当当前",step=dict(capability="home",target="回桌面",locator="none",bounds=None))
  with patch.object(r,"call_planner",side_effect=model):
   value=r.observe_plan(b"current-home",hint,info,vision_model=image)
  self.assertEqual(value["step"]["capability"],"open_app");self.assertEqual(len(seen),1)
