import unittest,os
from unittest.mock import patch
from display_service import store_policy
class StorePolicyTests(unittest.TestCase):
 def test_task_is_pinned_and_disabled_by_default(self):
  with patch.dict(os.environ,{},clear=True):self.assertFalse(store_policy.enabled(store_policy.TASK))
  with patch.dict(os.environ,{'EPAPER_STORE_DIAGNOSTIC':'meituan'}):
   self.assertTrue(store_policy.enabled(store_policy.TASK));self.assertFalse(store_policy.enabled('打开应用宝下载其他应用并打开'))
 def test_no_payment_login_other_app_or_adb_text(self):
  for label,action in [('支付','click'),('登录','click'),('其他应用','click'),('搜索','type_text'),('meituan','click'),('允许定位','click')]:
   with self.subTest(label=label),self.assertRaises(ValueError):store_policy.validate(dict(safe=True,target_label=label,action=action))
 def test_known_install_and_keyboard_targets(self):
  for label in ('应用宝','美团','安装','搜索','m'):
   self.assertEqual(store_policy.validate(dict(safe=True,target_label=label,action='click')),label)
 def test_normal_navigation_still_rejects_install(self):
  from display_service.general_nav import parse_task,GeneralNavigator
  with patch.dict(os.environ,{},clear=True):self.assertIsNone(parse_task(store_policy.TASK))

 def test_visible_app_icon_never_counts_as_open_completion(self):
  self.assertFalse(store_policy.completion_candidate(dict(complete=True,action="click",target_label="应用宝")))
  self.assertTrue(store_policy.completion_candidate(dict(complete=True,action="unknown")))

 def test_jev_point_guard_rejects_low_target_probability(self):
  import io,json
  from PIL import Image
  img=io.BytesIO();Image.new('RGB',(640,1280),'white').save(img,format='JPEG')
  candidate=dict(action='click',safe=True,target_label='应用宝',bounds=[600,300,750,430])
  class Response(io.BytesIO):
   def __enter__(self):return self
   def __exit__(self,*args):self.close()
  class Opener:
   def __init__(self,p):self.p=p
   def open(self,*args,**kwargs):return Response(json.dumps({'model':'synthetic','usage':None,'answers':{'allowed':{'type':'noul','noul':.99},'target':{'type':'noul','noul':self.p}}}).encode())
  with patch.object(store_policy.Path,'read_text',return_value='{"api_key":"synthetic-only"}'):
   with patch.object(store_policy.urllib.request,'build_opener',return_value=Opener(.94)):
    with self.assertRaises(ValueError):store_policy.judge(img.getvalue(),candidate)
   with patch.object(store_policy.urllib.request,'build_opener',return_value=Opener(.96)):
    self.assertEqual(store_policy.judge(img.getvalue(),candidate),candidate)

 def test_installation_rejects_other_board_before_any_action(self):
  from types import SimpleNamespace
  with patch.dict(os.environ,{"EPAPER_STORE_DIAGNOSTIC":"meituan"}),self.assertRaises(ValueError):store_policy.run(None,SimpleNamespace(device="other-board"),store_policy.TASK)

 def test_click_guard_uses_new_frame_after_planning(self):
  from types import SimpleNamespace
  from unittest.mock import Mock
  candidate=dict(action='click',safe=True,target_label='应用宝',bounds=[100,100,200,200])
  sig=lambda n:dict(w=640,h=1280,n=n)
  nav=SimpleNamespace(store=SimpleNamespace(invalidate=lambda device:None),_frame=Mock(side_effect=[(b'entry',1,sig(1)),(b'planned',2,sig(2)),(b'fresh',3,sig(3))]),_action=Mock(side_effect=[None,RuntimeError('sent')]),_observe=Mock(return_value=candidate),_command=Mock(return_value={'op':'hid_pointer'}),_log=Mock())
  with patch.dict(os.environ,{'EPAPER_STORE_DIAGNOSTIC':'meituan','EPAPER_STORE_JUDGE':'jev'}),patch.object(store_policy,'judge',return_value=candidate) as guard,patch.object(store_policy,'pointer_action',side_effect=RuntimeError('sent')) as execute:
   with self.assertRaisesRegex(RuntimeError,'sent'):store_policy.run(nav,SimpleNamespace(device='epaper-01'),store_policy.TASK)
   self.assertEqual(guard.call_args.args[0],b'fresh');self.assertEqual(execute.call_args.args[3],b'fresh')

 def test_mutating_steps_keep_strict_point_threshold(self):
  self.assertEqual(store_policy.point_threshold(dict(target_label='安装',confidence=1)),.95)
  self.assertEqual(store_policy.point_threshold(dict(target_label='下载',confidence=1)),.95)
  self.assertEqual(store_policy.point_threshold(dict(target_label='搜索框',confidence=.95)),.9)
  self.assertEqual(store_policy.point_threshold(dict(target_label='搜索框',confidence=.94)),.95)
 def test_search_anchor_stays_inside_model_observed_region(self):
  o=dict(target_label='搜索框',bounds=[131,46,748,84]);a=store_policy.anchor(o)
  self.assertEqual(a['bounds'],[131,46,254,84]);self.assertEqual(o['bounds'],[131,46,748,84])

 def test_search_focus_is_bounded_to_confident_top_input(self):
  good=dict(action='click',target_label='搜索框',confidence=.95,bounds=[131,46,254,84])
  self.assertTrue(store_policy.is_search_focus(good))
  for change in ({'confidence':.94},{'target_label':'安装'},{'bounds':[131,600,254,684]},{'action':'type_text'}):self.assertFalse(store_policy.is_search_focus(dict(good,**change)))

 def test_model_only_mode_never_calls_jev(self):
  from types import SimpleNamespace
  from unittest.mock import Mock
  candidate=dict(action='click',safe=True,confidence=1,target_label='应用宝',bounds=[100,100,200,200])
  sig=dict(w=640,h=1280)
  nav=SimpleNamespace(store=SimpleNamespace(invalidate=lambda device:None),_frame=Mock(side_effect=[(b'entry',1,sig),(b'planned',2,sig),(b'fresh',3,sig)]),_action=Mock(),_observe=Mock(return_value=candidate),_command=Mock(return_value={'op':'hid_pointer'}),_log=Mock())
  with patch.dict(os.environ,{'EPAPER_STORE_DIAGNOSTIC':'meituan','EPAPER_STORE_JUDGE':'off'}),patch.object(store_policy,'judge') as judge,patch.object(store_policy,'pointer_action',side_effect=RuntimeError('sent')):
   with self.assertRaisesRegex(RuntimeError,'sent'):store_policy.run(nav,SimpleNamespace(device='epaper-01'),store_policy.TASK)
   judge.assert_not_called()

 def test_model_only_rejects_out_of_scope_observation_before_pointer(self):
  from types import SimpleNamespace
  from unittest.mock import Mock
  for change in ({'target_label':'支付'}, {'safe':False}, {'action':'drag','target_label':'安装'}):
   with self.subTest(change=change):
    candidate=dict(action='click',safe=True,confidence=1,target_label='美团',bounds=[100,100,200,200]);candidate.update(change)
    sig=dict(w=640,h=1280)
    nav=SimpleNamespace(store=SimpleNamespace(invalidate=Mock()),_frame=Mock(side_effect=[(b'entry',1,sig),(b'planned',2,sig),(b'fresh',3,sig)]),_action=Mock(),_observe=Mock(return_value=candidate),_command=Mock(return_value={'op':'hid_pointer'}),_log=Mock())
    with patch.dict(os.environ,{'EPAPER_STORE_DIAGNOSTIC':'meituan','EPAPER_STORE_JUDGE':'off'}),patch.object(store_policy,'pointer_action') as execute:
     with self.assertRaises(ValueError):store_policy.run(nav,SimpleNamespace(device='epaper-01'),store_policy.TASK)
     execute.assert_not_called();nav._command.assert_not_called()
