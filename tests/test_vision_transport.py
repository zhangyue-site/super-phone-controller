"""Subscription transport never chooses a backup or replays a stale frame."""
import contextlib,errno,io,json,os,unittest,urllib.error
from unittest.mock import patch
from display_service.general_vision import request_vision,VisionTransportError,_vision_url
class VisionTransportTests(unittest.TestCase):
 def setUp(self):self.cfg={'baseUrl':'https://legacy.invalid/v1','apiKey':'synthetic-only'};self.payload={'model':'mimo-v2.6-flash'}
 def test_success_preserves_usage_on_exact_go_route(self):
  usage={'prompt_tokens':10,'completion_tokens':2,'total_tokens':12}
  with patch('display_service.general_vision._open_vision',return_value=io.BytesIO(json.dumps({'usage':usage}).encode())) as net:
   value,req,provider,_=request_vision(self.payload,'opencode-go','mimo-v2.6-flash',self.cfg)
   self.assertEqual(value['usage'],usage);self.assertEqual(provider,'opencode-go');self.assertEqual(req.full_url,'https://opencode.ai/inference/go/openai/v1/chat/completions');self.assertEqual(net.call_count,1)
 def test_retryable_errors_are_typed_but_transport_does_not_retry(self):
  for error in (TimeoutError(),OSError(),urllib.error.HTTPError('synthetic',429,'',{},None),urllib.error.HTTPError('synthetic',503,'',{},None)):
   with self.subTest(error=type(error).__name__),patch('display_service.general_vision._open_vision',side_effect=error) as net:
    with self.assertRaises(VisionTransportError) as caught:request_vision(self.payload,'opencode-go','mimo-v2.6-flash',self.cfg)
    self.assertTrue(caught.exception.retryable);self.assertEqual(net.call_count,1)
 def test_auth_and_request_errors_never_retry_or_fallback(self):
  for status in (400,401,403):
   with self.subTest(status=status),patch('display_service.general_vision._open_vision',side_effect=urllib.error.HTTPError('synthetic',status,'',{},None)) as net:
    with self.assertRaises(VisionTransportError) as caught:request_vision(self.payload,'opencode-go','mimo-v2.6-flash',self.cfg)
    self.assertFalse(caught.exception.retryable);self.assertEqual(net.call_count,1)
 def test_legacy_fallback_env_cannot_enable_cross_provider(self):
  with patch.dict(os.environ,{'EPAPER_VISION_FALLBACK_PROVIDER':'xiaomi','EPAPER_VISION_FALLBACK_TIMEOUT_SECONDS':'45'}),patch('display_service.general_vision._open_vision',side_effect=TimeoutError()) as net:
   with self.assertRaises(VisionTransportError) as caught:request_vision(self.payload,'opencode-go','mimo-v2.6-flash',self.cfg)
   self.assertEqual(caught.exception.provider,'opencode-go');self.assertEqual(net.call_count,1);self.assertEqual(net.call_args.kwargs['timeout'],30)
 def test_non_go_timeout_never_migrates_to_go(self):
  with patch('display_service.general_vision._open_vision',side_effect=TimeoutError()) as net:
   with self.assertRaises(VisionTransportError) as caught:request_vision(self.payload,'xiaomi','mimo-v2.6-flash',self.cfg)
   self.assertFalse(caught.exception.retryable);self.assertEqual(net.call_count,1)
 def test_invalid_json_is_not_retryable_transport(self):
  with patch('display_service.general_vision._open_vision',return_value=io.BytesIO(b'not json')) as net:
   with self.assertRaises(json.JSONDecodeError):request_vision(self.payload,'opencode-go','mimo-v2.6-flash',self.cfg)
   self.assertEqual(net.call_count,1)

 def failure_log(self,error,*,response=None):
  output=io.StringIO()
  options={'return_value':response} if response is not None else {'side_effect':error}
  with contextlib.redirect_stdout(output),patch('display_service.general_vision._open_vision',**options) as net,patch('display_service.general_vision.time.monotonic',side_effect=[10,28.125]):
   with self.assertRaises(VisionTransportError) as caught:
    request_vision(self.payload,'opencode-go','mimo-v2.6-flash',self.cfg)
  rows=[json.loads(line.split(' ',1)[1]) for line in output.getvalue().splitlines() if line.startswith('VISION_TRANSPORT_ERROR ')]
  self.assertEqual(len(rows),1);self.assertEqual(net.call_count,1)
  self.assertNotIn('synthetic-only',output.getvalue())
  self.assertNotIn('private-failure-detail',output.getvalue())
  self.assertTrue(hasattr(caught.exception,'timed_out'))
  self.assertIn('phase',rows[0])
  return caught.exception,rows[0],output.getvalue()
 def test_open_timeout_reports_phase_and_accurate_message(self):
  for error in (TimeoutError(errno.ETIMEDOUT,'private-failure-detail'),urllib.error.URLError(TimeoutError(errno.ETIMEDOUT,'private-failure-detail'))):
   with self.subTest(wrapped=isinstance(error,urllib.error.URLError)):
    caught,log,_=self.failure_log(error)
    self.assertIn('视觉识别请求超时',str(caught));self.assertTrue(caught.timed_out)
    self.assertEqual(log['phase'],'open');self.assertEqual(log['elapsed_ms'],18125);self.assertEqual(log['timeout_s'],30)
    self.assertEqual(log['reason_type'],'TimeoutError');self.assertEqual(log['errno'],errno.ETIMEDOUT)
    self.assertEqual(log['category'],'timeout');self.assertTrue(caught.retryable)
    self.assertEqual(caught.config,self.cfg);self.assertEqual(caught.provider,'opencode-go')
 def test_read_timeout_reports_phase_and_closes_response(self):
  class SlowBody(io.BytesIO):
   def read(self,*args):raise TimeoutError('private-failure-detail')
  body=SlowBody()
  caught,log,_=self.failure_log(None,response=body)
  self.assertTrue(body.closed);self.assertTrue(caught.timed_out)
  self.assertEqual(log['phase'],'read');self.assertEqual(log['reason_type'],'TimeoutError')
  self.assertIsNone(log['errno']);self.assertEqual(log['elapsed_ms'],18125)
 def test_non_timeout_retains_original_message_and_safe_errno(self):
  caught,log,_=self.failure_log(ConnectionResetError(errno.ECONNRESET,'private-failure-detail'))
  self.assertEqual(str(caught),'视觉识别服务连接失败，本次停止；请稍后重试。')
  self.assertFalse(caught.timed_out);self.assertEqual(log['category'],'connection')
  self.assertEqual(log['reason_type'],'ConnectionResetError');self.assertEqual(log['errno'],errno.ECONNRESET)
 def test_untrusted_reason_and_errno_are_not_logged(self):
  error=urllib.error.URLError('https://private-failure-detail.invalid/?token=private-failure-detail')
  error.errno='private-failure-detail'
  caught,log,_=self.failure_log(error)
  self.assertFalse(caught.timed_out);self.assertEqual(log['type'],'URLError')
  self.assertIsNone(log['reason_type']);self.assertIsNone(log['errno'])
  self.assertEqual(set(log),{'provider','type','status','retryable','retry','phase','elapsed_ms','timeout_s','category','reason_type','errno'})
 def test_unknown_exception_subclass_name_is_not_logged(self):
  error_type=type('private-failure-detail',(OSError,),{})
  caught,log,_=self.failure_log(error_type('private-failure-detail'))
  self.assertEqual(log['type'],'OSError');self.assertEqual(log['reason_type'],'OSError')
  self.assertEqual(log['category'],'io');self.assertFalse(caught.timed_out)
 def test_http_failure_keeps_usage_without_logging_error_body(self):
  body=io.BytesIO(json.dumps({'usage':{'total_tokens':3},'detail':'private-failure-detail'}).encode())
  caught,log,output=self.failure_log(urllib.error.HTTPError('https://private-failure-detail.invalid',503,'private-failure-detail',{},body))
  usage=[json.loads(line.split(' ',1)[1]) for line in output.splitlines() if line.startswith('VISION_USAGE ')][0]
  self.assertEqual(usage['usage'],{'total_tokens':3});self.assertEqual(log['status'],503)
  self.assertEqual(log['type'],'HTTPError');self.assertEqual(log['category'],'http')
  self.assertFalse(caught.timed_out);self.assertTrue(caught.retryable)
 def test_existing_exception_constructor_is_compatible(self):
  error=VisionTransportError('opencode-go','mimo-v2.6-flash',self.cfg,True)
  self.assertTrue(hasattr(error,'timed_out'))
  self.assertFalse(error.timed_out);self.assertEqual(error.config,self.cfg)
  self.assertEqual(str(error),'视觉识别服务连接失败，本次停止；请稍后重试。')

 def test_go_waits_longer_without_changing_other_providers(self):
  for provider,timeout in (('opencode-go',30),('xiaomi',18)):
   with self.subTest(provider=provider),patch('display_service.general_vision._open_vision',return_value=io.BytesIO(b'{}')) as net:
    _,request,actual,_=request_vision(self.payload,provider,'mimo-v2.6-flash',self.cfg)
    self.assertEqual(net.call_count,1);self.assertEqual(net.call_args.kwargs['timeout'],timeout)
    self.assertEqual(actual,provider)
    expected='https://opencode.ai/inference/go/openai/v1/chat/completions' if provider=='opencode-go' else self.cfg['baseUrl']+'/chat/completions'
    self.assertEqual(request.full_url,expected)
 def test_non_go_timeout_log_reports_unchanged_wait(self):
  output=io.StringIO()
  with contextlib.redirect_stdout(output),patch('display_service.general_vision._open_vision',side_effect=TimeoutError()) as net:
   with self.assertRaises(VisionTransportError) as caught:request_vision(self.payload,'xiaomi','mimo-v2.6-flash',self.cfg)
  row=[json.loads(line.split(' ',1)[1]) for line in output.getvalue().splitlines() if line.startswith('VISION_TRANSPORT_ERROR ')][0]
  self.assertEqual(row['timeout_s'],18);self.assertFalse(caught.exception.retryable);self.assertTrue(caught.exception.timed_out)
  self.assertEqual(net.call_count,1)
