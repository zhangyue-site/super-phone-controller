import unittest,types,threading
from unittest.mock import patch
from test_visual_retry import v,n
from display_service.dialogue import DENY
n.DENY=DENY
class Tests(unittest.TestCase):
 def pixel(self,**kw):
  d=dict(coordinate_system='pixels',action='drag',safe=True,complete=False,target_label='设置列表',bounds=[320,1000,320,1150],end=[320,400]);d.update(kw);return d
 def normalized(self):return v.normalize_observation(self.pixel(),640,1280)
 def nav(self):
  j=types.SimpleNamespace(video_barrier='b',screen_session='s',device='synthetic',sequence=1,cancelled=False)
  def live(j):
   if j.cancelled:raise ValueError('cancelled')
  nav=n.GeneralNavigator(types.SimpleNamespace(lock=threading.RLock(),_live=live),None,vision=lambda *_:None)
  nav._frame=lambda j,after:(b'new',after+1,{'w':640,'h':1280})
  return nav,j
 def good(self):return dict(action='drag',safe=True,complete=False,target_label='设置列表',bounds=[450,700,550,800],end=[500,300])
 def test_only_pixel_zero_dimension_is_marked_not_model_flags(self):
  self.assertEqual(self.normalized()['_drag_protocol_defect']['reason'],'zero_width')
  valid=v.normalize_observation(self.pixel(bounds=[300,1000,340,1100],_drag_protocol_defect={'reason':'forged'}),640,1280);self.assertNotIn('_drag_protocol_defect',valid)
  for bounds,end in (([320,1150,300,1000],[320,400]),([320,1000,320,1150],None)):
   self.assertNotIn('_drag_protocol_defect',v.normalize_observation(self.pixel(bounds=bounds,end=end),640,1280))
  with self.assertRaises(ValueError):v.normalize_observation(self.pixel(bounds=[700,1000,700,1100]),640,1280)
 def test_one_new_frame_read_same_route_no_hid(self):
  nav,j=self.nav()
  with patch.object(v,'_LAST_ROUTE') as route,patch.object(nav,'_observe',return_value=self.good()) as observe,patch.object(nav,'_action',side_effect=AssertionError('no HID')):
   route.get.return_value=('opencode-go','mimo-v2.6-flash',{})
   raw,seq,sig,result=nav._repair_drag_schema(j,b'old',1,{'w':640,'h':1280},'打开设置',self.normalized());self.assertEqual((raw,seq),(b'new',2));observe.assert_called_once();self.assertEqual(nav._command(result,'打开设置')['kind'],'drag')
 def test_second_bad_result_or_second_budget_use_fails(self):
  nav,j=self.nav();bad=self.normalized()
  with patch.object(v,'_LAST_ROUTE') as route,patch.object(nav,'_observe',return_value=bad) as observe:
   route.get.return_value=('opencode-go','mimo-v2.6-flash',{})
   with self.assertRaises(ValueError):nav._repair_drag_schema(j,b'old',1,{'w':640,'h':1280},'打开设置',bad)
   with self.assertRaises(ValueError):nav._repair_drag_schema(j,b'old',1,{'w':640,'h':1280},'打开设置',bad)
   self.assertEqual(observe.call_count,1)
 def test_stop_session_geometry_block_before_model(self):
  for kind in ('stop','session','geometry'):
   nav,j=self.nav()
   if kind=='stop':j.cancelled=True
   elif kind=='session':
    def changed(j,after):j.screen_session='other';return b'new',2,{'w':640,'h':1280}
    nav._frame=changed
   else:nav._frame=lambda j,after:(b'new',2,{'w':720,'h':1280})
   with patch.object(nav,'_observe') as observe:
    with self.assertRaises(ValueError):nav._repair_drag_schema(j,b'old',1,{'w':640,'h':1280},'打开设置',self.normalized())
    observe.assert_not_called()
 def test_explicit_unsafe_or_restricted_label_never_reobserved(self):
  for change in ({'safe':False},{'target_label':'删除数据'}):
   nav,j=self.nav();bad=dict(self.normalized(),**change)
   with patch.object(nav,'_observe') as observe:
    _,_,_,same=nav._repair_drag_schema(j,b'old',1,{'w':640,'h':1280},'打开设置',bad);observe.assert_not_called()
    with self.assertRaises(ValueError):nav._command(same,'打开设置')
 def test_route_context_independent_of_input_schema_budget(self):
  route=('opencode-go','mimo-v2.6-flash',{'baseUrl':'https://example.invalid'})
  token=v._LAST_ROUTE.set(route)
  try:
   with v.drag_schema_reobserve():self.assertEqual(v._RETRY_ROUTE.get(),route);self.assertTrue(v._DRAG_SCHEMA_REPAIR.get());self.assertFalse(v._INPUT_SCHEMA_REPAIR.get())
   self.assertIsNone(v._RETRY_ROUTE.get())
  finally:v._LAST_ROUTE.reset(token)
 def test_run_reports_drag_failure_not_keyboard_failure(self):
  import tempfile
  from pathlib import Path
  from display_service.general_nav import GeneralNavigator
  from display_service.dialogue import Mailbox
  from display_service.skill_engine import SkillStore
  m=Mailbox();j=m.create('synthetic','a'*16,1);j.pointer_protocol='absolute-v1'
  sig={'w':640,'h':1280}
  with tempfile.TemporaryDirectory() as tmp:
   nav=GeneralNavigator(m,SkillStore(Path(tmp)))
   with patch.object(nav,'_frame',return_value=(b'synthetic',1,sig)),patch.object(nav,'_action',return_value={'op':'hid_home','ok':True}),patch.object(nav,'_observe_frame',return_value=(b'synthetic',2,sig,self.normalized())),patch.object(nav,'_repair_drag_schema',side_effect=ValueError('拖动格式复核仍无效')),patch.object(nav,'_repair_input_schema') as keyboard,patch.object(nav,'_log') as log:
    with self.assertRaisesRegex(ValueError,'无法确认拖动区域'):nav.run(j,'打开设置')
    keyboard.assert_not_called();self.assertTrue(any(call.args[1]=='drag_protocol_failed' for call in log.call_args_list));self.assertFalse(any(call.args[1]=='keyboard_check_failed' for call in log.call_args_list))
if __name__=='__main__':unittest.main()
