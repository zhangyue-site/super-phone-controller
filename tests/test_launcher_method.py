import unittest
from unittest.mock import patch
from display_service.general_vision import launcher_method,normalize_observation

class LauncherMethodTests(unittest.TestCase):
 def result(self,**values):
  d=dict(confidence=.95,safe=True,complete=False,screen='安卓桌面',action='click',target_label='计算器',bounds=[10,20,30,40]);d.update(values);return d
 def test_desktop_icon_positions_do_not_define_the_app_method(self):
  for box,screen in (([10,20,30,40],'安卓桌面'),([700,700,900,900],'Android桌面')):
   with patch('display_service.jev_vision.clear_swipe_region',return_value=True):r=launcher_method(self.result(bounds=box,screen=screen),b'frame','打开计算器')
   self.assertEqual(r['action'],'drag');self.assertEqual(r['bounds'],[450,630,550,670]);self.assertTrue(r['_trusted_launcher_blank'])
 def test_nonblank_region_never_gets_server_certification(self):
  o=self.result()
  with patch('display_service.jev_vision.clear_swipe_region',return_value=False):self.assertIs(launcher_method(o,b'frame','打开计算器'),o)
 def test_bad_page_confidence_or_complete_never_creates_action(self):
  for values in ({'screen':'浏览器'},{'confidence':.89},{'confidence':float('nan')},{'safe':False},{'complete':True},{'action':'unknown'}):
   o=self.result(**values)
   with self.subTest(values=values),patch('display_service.jev_vision.clear_swipe_region',return_value=True):self.assertIs(launcher_method(o,b'frame','打开计算器'),o)
 def test_only_safe_app_opening_uses_method(self):
  for task in ('回到手机桌面','删除照片','打开设置并卸载应用','打开设置'):
   o=self.result()
   with self.subTest(task=task),patch('display_service.jev_vision.clear_swipe_region',return_value=True):self.assertIs(launcher_method(o,b'frame',task),o)
 def test_model_cannot_inject_trusted_desktop_flag(self):
  r=normalize_observation(dict(self.result(),coordinate_system='pixels',_trusted_launcher_blank=True),1000,1000);self.assertNotIn('_trusted_launcher_blank',r)
