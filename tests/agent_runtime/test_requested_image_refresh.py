import unittest,json
from unittest.mock import patch
from display_service import agent_runtime as r
from display_service.agent_observation import bind_visual
import test_verify_contract as fixtures
class RequestedImage(unittest.TestCase):
 def test_partial_scene_does_not_suppress_explicit_image_request(self):
  hint,info=fixtures.VerificationContract().fixtures("tap_text")
  info["_visual_evidence"]=bind_visual(hint,dict(scene="桌面，未识别Dock",widgets=[],regions=[]))
  images=[]
  def image(payload):
   images.append(payload)
   return dict(scene="Android桌面含Dock",widgets=[dict(label="浏览器",role="app_icon",bounds=[180,1100,275,1200])],regions=[])
  def model(payload):
   data=json.loads(payload["messages"][1]["content"][0]["text"])
   if any(x.get("label")=="浏览器"for x in data.get("visual_observation",{}).get("widgets",[])):
    return dict(safe=True,done=False,evidence="本帧底栏有浏览器",step=dict(capability="open_app",target="浏览器",locator="icon",bounds=[180,1100,275,1200]))
   return dict(safe=True,done=False,need_image=True,evidence="已有局部事实不足以辨认Dock，请补当前图像",step=None)
  with patch.object(r,"call_planner",side_effect=model):
   value=r.observe_plan(b"current-home",hint,info,vision_model=image)
  self.assertEqual(value["step"]["capability"],"open_app");self.assertEqual(len(images),1)
