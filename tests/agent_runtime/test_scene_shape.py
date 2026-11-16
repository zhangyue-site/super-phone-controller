import unittest
from display_service.agent_perception import perceive
class SceneShape(unittest.TestCase):
 def call(self,scene,**extra):
  out=dict(scene=scene,widgets=[dict(label="亮度",role="brightness_slider",bounds=[300,320,410,550])],regions=[]);out.update(extra)
  return perceive(b"synthetic",dict(width=588,height=1280,lines=[]),{},model=lambda p:out)
 def test_structured_scene_is_fact_description_not_missing_image(self):
  value=self.call(dict(title="系统控制中心",page_type="system_panel",app="unknown"))
  self.assertIsInstance(value["scene"],str);self.assertIn("系统控制中心",value["scene"]);self.assertIn("system_panel",value["scene"]);self.assertEqual(len(value["widgets"]),1)
 def test_unknown_structure_cannot_invent_an_app(self):
  self.assertEqual(self.call(dict(confidence=.8))["scene"],"unknown")
 def test_nested_action_is_not_an_observation(self):
  with self.assertRaises(ValueError):self.call(dict(title="设置",action="点击同意"))
 def test_coordinate_and_top_level_action_guards_remain_strict(self):
  for extra in [dict(step=dict(capability="tap_text")),dict(widgets=[dict(label="亮度",role="brightness_slider",bounds=[-1,0,700,500])])]:
   with self.assertRaises(ValueError):self.call("控制中心",**extra)
if __name__=="__main__":unittest.main()
