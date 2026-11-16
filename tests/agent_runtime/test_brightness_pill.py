import unittest
from display_service.agent_runtime import _locate as locate
from display_service.agent_observation import capture,bind_visual
from display_service.agent_contract import Authority
class Pill(unittest.TestCase):
 def call(self,bounds,label="太阳标识屏幕亮度",regions=None,lines=None):
  a=Authority("t","d","s","l",frozenset({"observe"}),100)
  h=capture(a,1,b"synthetic",dict(width=588,height=1280,source="phone-ocr",lines=lines or []),observed_at=1).hint()
  v=bind_visual(h,dict(scene="控制中心",widgets=[dict(label=label,role="brightness_slider",bounds=bounds,observed_percent=50,observed_source="current_jpeg_pixel_boundary")],regions=regions or []))
  return locate(dict(capability="adjust_brightness",target=label,locator="icon",bounds=bounds,value_percent=40),h,visual_evidence=v)[0]
 def test_observed_vertical_pill_has_unambiguous_axis(self):
  c=self.call([294,324,404,554]);self.assertEqual(c["kind"],"drag");self.assertEqual(c["x"],round(349*32767/588));self.assertEqual(c["y2"],round(462*32767/1280))
 def test_horizontal_pill_uses_fraction_from_left(self):
  c=self.call([40,200,270,310]);self.assertEqual(c["kind"],"drag");self.assertEqual(c["x2"],round(132*32767/588));self.assertEqual(c["y"],round(255*32767/1280))
 def test_square_remains_ambiguous(self):
  with self.assertRaises(ValueError):self.call([100,100,250,270])
 def test_volume_cannot_use_brightness_tool_even_if_role_was_misclassified(self):
  for b in ([424,324,533,554],[424,324,533,724]):
   with self.assertRaises(ValueError):self.call(b,"耳机音量滑条")
 def test_modal_brightness_panel_allows_only_contained_slider(self):
  self.assertEqual(self.call([230,408,358,696],regions=[dict(role="dialog",bounds=[55,345,533,940])])["kind"],"drag")
 def test_background_slider_cannot_bypass_foreground_dialog(self):
  with self.assertRaises(ValueError):self.call([230,408,358,696],regions=[dict(role="dialog",bounds=[10,10,200,200])])
 def test_two_overlapping_dialogs_remain_blocked(self):
  with self.assertRaises(ValueError):self.call([230,408,358,696],regions=[dict(role="dialog",bounds=[0,0,588,1280]),dict(role="dialog",bounds=[55,345,533,940])])
 def test_permission_request_remains_blocked_even_with_real_slider(self):
  with self.assertRaises(ValueError):self.call([230,408,358,696],regions=[dict(role="dialog",bounds=[55,345,533,940])],lines=[dict(text="是否允许访问",bounds=[70,350,400,380])])
if __name__=="__main__":unittest.main()
