import unittest,types,sys,threading,urllib.error,io,json,contextlib,importlib
from pathlib import Path
from unittest.mock import patch
pkg=types.ModuleType('candidate');pkg.__path__=[str(Path(__file__).parent/'display_service')];sys.modules['candidate']=pkg
for name in ('model_routing','wechat_nav','dialogue','skill_engine'):
 m=types.ModuleType('candidate.'+name);sys.modules[m.__name__]=m
sys.modules['candidate.model_routing'].task_model_session=lambda f:f
sys.modules['candidate.model_routing'].vision_route=lambda:('opencode-go','mimo-v2.6-flash',{})
sys.modules['candidate.model_routing'].request_headers=lambda cfg:{}
sys.modules['candidate.dialogue'].PhoneCommandError=type('PhoneCommandError',(ValueError,),{});sys.modules['candidate.dialogue'].DENY=None
class Base:
 def __init__(self,mailbox,store,vision,frame_timeout):self.m=mailbox;self.vision=vision
 def _observe(self,j,raw,query,verify=False):return self.vision(raw,query,verify)
sys.modules['candidate.wechat_nav'].WechatNavigator=Base
s=sys.modules['candidate.skill_engine'];s.WorkflowSpec=lambda *a:None;s.region=s.matches=s.region_matches=lambda *a:None
from candidate import general_vision as v,general_nav as n
class Tests(unittest.TestCase):
 def request(self,error,provider='opencode-go'):
  with patch.object(v,'_open_vision',side_effect=error):
   return v.request_vision({'model':'mimo-v2.6-flash'},provider,'mimo-v2.6-flash',{'baseUrl':'https://example.invalid'})
 def test_retryable_transport(self):
  for error in (TimeoutError(),OSError(),urllib.error.HTTPError('x',429,'',{},None),urllib.error.HTTPError('x',503,'',{},None)):
   with self.assertRaises(v.VisionTransportError) as caught:self.request(error)
   self.assertTrue(caught.exception.retryable)
 def test_nonretryable_and_no_fallback(self):
  with patch.dict('os.environ',{'EPAPER_VISION_FALLBACK_PROVIDER':'xiaomi'}):
   with self.assertRaises(v.VisionTransportError) as caught:self.request(urllib.error.HTTPError('x',401,'',{},None))
   self.assertFalse(caught.exception.retryable)
  with self.assertRaises(v.VisionTransportError) as caught:self.request(TimeoutError(),'xiaomi')
  self.assertFalse(caught.exception.retryable)
 def nav(self,vision,cancel=False):
  j=types.SimpleNamespace(video_barrier='b',screen_session='s',device='test',sequence=1)
  def live(_):
   if cancel:raise ValueError('cancelled')
  nav=n.GeneralNavigator(types.SimpleNamespace(lock=threading.RLock(),_live=live),None,vision=vision)
  nav._frame=lambda j,after:(b'new',after+1,{'fresh':True})
  return nav,j
 def transient(self):return v.VisionTransportError('opencode-go','mimo-v2.6-flash',{'baseUrl':'https://example.invalid'},True)
 def test_fresh_frame_retry_and_bound(self):
  calls=[]
  def observe(raw,*_):
   calls.append(raw)
   if len(calls)==1:raise self.transient()
   return {'safe':True}
  nav,j=self.nav(observe);raw,seq,sig,result=nav._observe_frame(j,b'old',1,{},'query')
  self.assertEqual(calls,[b'old',b'new']);self.assertEqual((raw,seq),(b'new',2))
  count=[]
  def fail(*_):count.append(1);raise self.transient()
  nav,j=self.nav(fail)
  with self.assertRaises(v.VisionTransportError):nav._observe_frame(j,b'old',1,{},'query')
  self.assertEqual(len(count),2)
 def test_cancel_and_semantics_no_retry(self):
  calls=[]
  nav,j=self.nav(lambda *_:calls.append(1),cancel=True)
  with self.assertRaises(ValueError):nav._observe_frame(j,b'old',1,{},'query')
  self.assertEqual(calls,[])
  def bad(*_):calls.append(1);raise ValueError('semantic')
  nav,j=self.nav(bad)
  with self.assertRaises(ValueError):nav._observe_frame(j,b'old',1,{},'query')
  self.assertEqual(len(calls),1)
 def test_stop_during_failure_and_changed_session(self):
  nav,j=self.nav(lambda *_:None)
  def fail(*_):j.video_barrier='revoked';raise self.transient()
  nav.vision=fail
  with self.assertRaisesRegex(ValueError,'会话'):nav._observe_frame(j,b'old',1,{},'query')
 def test_same_provider_pinned_and_usage_on_failed_http(self):
  err=self.transient()
  with v.same_provider_retry(err):self.assertEqual(v._RETRY_ROUTE.get()[0],'opencode-go')
  self.assertIsNone(v._RETRY_ROUTE.get())
  body=io.BytesIO(json.dumps({'usage':{'prompt_tokens':12,'completion_tokens':2,'total_tokens':14}}).encode())
  error=urllib.error.HTTPError('x',503,'',{},body);output=io.StringIO()
  with contextlib.redirect_stdout(output):
   with self.assertRaises(v.VisionTransportError):self.request(error)
  rows=[json.loads(x.split(' ',1)[1]) for x in output.getvalue().splitlines() if x.startswith('VISION_USAGE ')]
  self.assertEqual(rows[0]['usage']['total_tokens'],14)
 def test_parse_error_not_retried(self):
  with patch.object(v,'_open_vision') as opener:
   opener.return_value.__enter__.return_value.read.return_value=b'not json'
   with self.assertRaises(json.JSONDecodeError):v.request_vision({},'opencode-go','mimo-v2.6-flash',{'baseUrl':'https://example.invalid'})
   self.assertEqual(opener.call_count,1)
if __name__=='__main__':unittest.main()
