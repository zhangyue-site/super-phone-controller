import unittest,types,threading
from unittest.mock import patch
from test_visual_retry import v,n
from candidate import keyboard_navigation as k
class Tests(unittest.TestCase):
 def good(self):return dict(action='type_text',safe=True,text='北京',input_visible=True,input_focused=True,input_password=False,input_role='search')
 def nav(self,answer):
  j=types.SimpleNamespace(video_barrier='b',screen_session='s',device='synthetic',sequence=1,cancelled=False)
  def live(j):
   if j.cancelled:raise ValueError('cancelled')
  nav=n.GeneralNavigator(types.SimpleNamespace(lock=threading.RLock(),_live=live),None,vision=lambda *_:answer)
  nav._frame=lambda j,after:(b'new',after+1,{})
  return nav,j
 def test_missing_types_are_repairable_but_negative_evidence_is_not(self):
  for field in ('input_visible','input_password','input_focused','input_role'):
   o=self.good();o.pop(field);self.assertEqual(k.schema_issue_fields(o),(field,))
  for field,value in (('input_visible',False),('input_focused',False),('input_password',True),('input_role','unknown'),('safe',False)):
   o=self.good();o.pop('input_visible',None);o[field]=value
   self.assertEqual(k.schema_issue_fields(o),())
   with self.assertRaises(ValueError):k.decision(None,o,'搜索北京',1)
 def test_one_fresh_frame_reobserve_without_any_hid(self):
  o=self.good();o.pop('input_visible');o.pop('input_password');nav,j=self.nav(self.good())
  route=('opencode-go','mimo-v2.6-flash',{'baseUrl':'https://example.invalid'})
  with patch.object(v,'_LAST_ROUTE') as last,patch.object(nav,'_observe',return_value=self.good()) as observed,patch.object(nav,'_action',side_effect=AssertionError('no HID')):
   last.get.return_value=route
   raw,seq,sig,result=nav._repair_input_schema(j,b'old',1,{},'搜索北京',o)
   self.assertEqual((raw,seq),(b'new',2));observed.assert_called_once();self.assertEqual(observed.call_args.args[1],b'new')
   self.assertEqual(k.decision(None,result,'搜索北京',seq)[0]['op'],'hid_text')
 def test_second_missing_schema_fails_without_repetition(self):
  bad=self.good();bad.pop('input_password');nav,j=self.nav(bad)
  with patch.object(v,'_LAST_ROUTE') as last,patch.object(nav,'_observe',return_value=bad) as observed:
   last.get.return_value=('opencode-go','mimo-v2.6-flash',{})
   with self.assertRaises(ValueError):nav._repair_input_schema(j,b'old',1,{},'搜索北京',bad)
   self.assertEqual(observed.call_count,1)
 def test_cancel_or_session_change_prevents_model_call(self):
  bad=self.good();bad.pop('input_visible');nav,j=self.nav(self.good());j.cancelled=True
  with patch.object(nav,'_observe') as observed:
   with self.assertRaises(ValueError):nav._repair_input_schema(j,b'old',1,{},'搜索北京',bad)
   observed.assert_not_called()
  j.cancelled=False
  def changed(j,after):j.screen_session='new';return b'new',2,{}
  nav._frame=changed
  with patch.object(nav,'_observe') as observed:
   with self.assertRaises(ValueError):nav._repair_input_schema(j,b'old',1,{},'搜索北京',bad)
   observed.assert_not_called()
 def test_wrong_types_need_observation_not_coercion(self):
  for field,value in (('input_visible','true'),('input_password','false'),('input_focused',1),('input_role',False)):
   o=self.good();o[field]=value;self.assertEqual(k.schema_issue_fields(o),(field,))
   with self.assertRaises(ValueError):k.decision(None,o,'搜索北京',1)
 def test_second_explicit_negative_is_rejected_by_unchanged_guard(self):
  bad=self.good();bad.pop('input_password');negative=self.good();negative['input_focused']=False;nav,j=self.nav(negative)
  with patch.object(v,'_LAST_ROUTE') as last:
   last.get.return_value=('opencode-go','mimo-v2.6-flash',{})
   raw,seq,sig,result=nav._repair_input_schema(j,b'old',1,{},'搜索北京',bad)
   with self.assertRaises(ValueError):k.decision(None,result,'搜索北京',seq)
  with patch.object(nav,'_observe') as observed:
   with self.assertRaises(ValueError):nav._repair_input_schema(j,b'old',seq,{},'搜索北京',bad)
   observed.assert_not_called()
 def test_schema_context_pins_route_and_does_not_allow_another_provider(self):
  route=('opencode-go','mimo-v2.6-flash',{'baseUrl':'https://example.invalid','apiKey':'synthetic-only'})
  token=v._LAST_ROUTE.set(route)
  try:
   with v.input_schema_reobserve():self.assertEqual(v._RETRY_ROUTE.get(),route);self.assertTrue(v._INPUT_SCHEMA_REPAIR.get())
   self.assertIsNone(v._RETRY_ROUTE.get());self.assertFalse(v._INPUT_SCHEMA_REPAIR.get())
  finally:v._LAST_ROUTE.reset(token)
  token=v._LAST_ROUTE.set(('xiaomi','mimo-v2.6-flash',{}))
  try:
   with self.assertRaises(ValueError):
    with v.input_schema_reobserve():pass
  finally:v._LAST_ROUTE.reset(token)
 def test_wrong_target_text_is_semantic_failure_not_schema_retry(self):
  bad=self.good();bad.pop('input_password');bad['text']='无关内容';nav,j=self.nav(self.good())
  with patch.object(nav,'_observe') as observed:
   _,_,_,result=nav._repair_input_schema(j,b'old',1,{},'搜索北京',bad)
   observed.assert_not_called()
   with self.assertRaises(ValueError):k.decision(None,result,'搜索北京',1)
if __name__=='__main__':unittest.main()
