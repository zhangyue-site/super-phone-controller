import unittest,json
from unittest.mock import patch
from display_service import agent_runtime as r
import test_verify_contract as fixtures
class AppEntry(unittest.TestCase):
 def test_text_folder_candidate_forces_current_image_before_launch(self):
  hint,info=fixtures.VerificationContract().fixtures("tap_text");images=[]
  def image(payload):
   images.append(payload)
   return dict(scene="已打开的应用文件夹，标题不是应用图标",widgets=[dict(label="中国移动",role="text",bounds=[20,160,200,180])],regions=[])
  def model(payload):
   data=json.loads(payload["messages"][1]["content"][0]["text"])
   if data.get("visual_observation"):
    return dict(safe=True,done=False,evidence="当前是文件夹标题，应返回查找真实浏览器",step=dict(capability="back",target="返回桌面",locator="none",bounds=None))
   return dict(safe=True,done=False,evidence="把文字标题误当App入口",step=dict(capability="open_app",target="中国移动",locator="text",bounds=[20,160,200,180]))
  with patch.object(r,"call_planner",side_effect=model):
   value=r.observe_plan(b"current-folder",hint,info,vision_model=image)
  self.assertEqual(value["step"]["capability"],"back");self.assertEqual(len(images),1)
