import os,unittest
from unittest.mock import patch
from types import SimpleNamespace
from display_service.conversation import Conversation
from display_service.dialogue import Mailbox
from display_service.general_vision import launcher_method,normalize_observation

class NoAdbRoutes(unittest.TestCase):
 def test_production_wechat_search_uses_usb_navigator(self):
  calls=[];m=Mailbox();j=m.create('d','0123456789abcdef',1);j.remote_task_id='test'
  nav=SimpleNamespace(run=lambda job,text:(calls.append(text) or '已核验'))
  legacy=SimpleNamespace(run=lambda *a:(_ for _ in ()).throw(AssertionError('legacy ADB path')))
  c=Conversation(mailbox=m,model=lambda *a:(_ for _ in ()).throw(AssertionError('chat fallback')),navigator=legacy,general_navigator=nav,skills=SimpleNamespace(invalidate=lambda *a:None),status=lambda *a:None)
  with patch.dict(os.environ,{'EPAPER_WECHAT_NAV':'1'}):c.run(j,'打开微信找到张三')
  self.assertEqual(calls,['打开微信搜索张三']);self.assertTrue(j.done)
 def test_settings_gets_same_safe_drawer_method(self):
  o=dict(safe=True,complete=False,screen='安卓桌面',action='drag',bounds=[1,1,2,2])
  with patch('display_service.jev_vision.clear_swipe_region',return_value=True):r=launcher_method(o,b'frame','打开设置')
  self.assertTrue(r['_trusted_launcher_blank']);self.assertEqual(r['bounds'],[450,630,550,670])
 def test_candidate_coordinates_use_original_pixels(self):
  o=normalize_observation(dict(coordinate_system='pixels',candidates=[dict(text='北京',bounds=[10,100,200,200])]),400,800)
  self.assertEqual(o['candidates'][0]['bounds'],[25,125,500,250])
  with self.assertRaises(ValueError):normalize_observation(dict(coordinate_system='pixels',candidates=[dict(text='北京',bounds=[0,0,1000,1000])]),400,800)

if __name__=='__main__':unittest.main()
