import copy,json,unittest
from unittest.mock import patch
from display_service import agent_runtime as r
from display_service.agent_contract import Authority
from display_service.agent_observation import capture

class VerificationContract(unittest.TestCase):
 def fixtures(self,cap="edge_swipe"):
  a=Authority("t","d","s","l",frozenset({"observe"}),100)
  hint=capture(a,1,b"current-control-panel",dict(width=588,height=1280,source="phone-ocr",lines=[dict(text=s,bounds=[20,120+i*40,200,140+i*40])for i,s in enumerate(["11月13日","中国移动","已连接","暂无播放"])]),observed_at=1).hint()
  info=dict(original="打开系统设置",goal="设置首页",scope={},stages=[],completion=["设置首页"],_platform="android",_last_action=dict(capability=cap,target="打开控制中心",receipt="confirmed"))
  return hint,info
 def visual(self,p):
  return dict(scene="系统控制中心",widgets=[],regions=[])
 def test_edge_verify_uses_current_visual_even_with_four_ocr_lines(self):
  hint,info=self.fixtures();requests=[];images=[]
  def planner(p):
   data=json.loads(p["messages"][1]["content"][0]["text"]);requests.append(data)
   if data.get("visual_observation",{}).get("scene")=="系统控制中心":return dict(safe=True,done=False,step_verified=True,evidence="控制中心已展开，但尚未到设置首页",step=None)
   return dict(safe=True,done=False,evidence="仅有日期运营商，猜测仍是桌面",step=None)
  def image(p):images.append(p);return self.visual(p)
  with patch.object(r,"call_planner",side_effect=planner):
   value=r.observe_plan(b"current-control-panel",hint,info,verify=True,vision_model=image)
  self.assertTrue(value.get("step_verified"));self.assertIsNone(value["step"]);self.assertFalse(value["done"]);self.assertEqual(len(images),1)
 def test_missing_step_field_repairs_read_only_once_without_returning_new_action(self):
  hint,info=self.fixtures("tap_text");calls=[]
  first=dict(safe=True,done=False,evidence="需要继续导航",step=dict(capability="edge_swipe",target="再拉",locator="edge",bounds=None,edge="top",anchor_percent=90,distance_percent=60))
  corrected=dict(safe=True,done=False,step_verified=True,evidence="前一步面板已展开，任务未完成",step=None)
  def planner(p):calls.append(p);return copy.deepcopy(first if len(calls)==1 else corrected)
  with patch.object(r,"call_planner",side_effect=planner):
   value=r.observe_plan(b"current-control-panel",hint,info,verify=True,vision_model=self.visual)
  self.assertEqual(len(calls),2);self.assertTrue(value.get("step_verified"));self.assertIsNone(value["step"])
 def test_persistently_invalid_verification_stops_without_returning_an_input(self):
  hint,info=self.fixtures("tap_text");calls=[]
  def planner(p):calls.append(p);return dict(safe=True,done=False,evidence="缺少核验字段",step=None)
  with patch.object(r,"call_planner",side_effect=planner):
   with self.assertRaises(ValueError):r.observe_plan(b"current-control-panel",hint,info,verify=True,vision_model=self.visual)
  self.assertEqual(len(calls),2)
 def test_non_boolean_verification_cannot_be_accepted_as_true(self):
  hint,info=self.fixtures("tap_text")
  with patch.object(r,"call_planner",return_value=dict(safe=True,done=False,step_verified="true",evidence="字符串不能作为核验",step=None)):
   with self.assertRaises(ValueError):r.observe_plan(b"current-control-panel",hint,info,verify=True,vision_model=self.visual)
if __name__=="__main__":unittest.main()
