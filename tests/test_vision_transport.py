"""Subscription transport never chooses a backup or replays a stale frame."""
import io,json,os,unittest,urllib.error
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
   self.assertEqual(caught.exception.provider,'opencode-go');self.assertEqual(net.call_count,1);self.assertEqual(net.call_args.kwargs['timeout'],18)
 def test_non_go_timeout_never_migrates_to_go(self):
  with patch('display_service.general_vision._open_vision',side_effect=TimeoutError()) as net:
   with self.assertRaises(VisionTransportError) as caught:request_vision(self.payload,'xiaomi','mimo-v2.6-flash',self.cfg)
   self.assertFalse(caught.exception.retryable);self.assertEqual(net.call_count,1)
 def test_invalid_json_is_not_retryable_transport(self):
  with patch('display_service.general_vision._open_vision',return_value=io.BytesIO(b'not json')) as net:
   with self.assertRaises(json.JSONDecodeError):request_vision(self.payload,'opencode-go','mimo-v2.6-flash',self.cfg)
   self.assertEqual(net.call_count,1)
