# Import the existing fully isolated retry fixture; no model traffic is possible.
from test_visual_retry import v
import unittest,urllib.request,urllib.error
from unittest.mock import patch
class EndpointTests(unittest.TestCase):
 def test_legacy_cfg_uses_official_new_go(self):
  self.assertEqual(v._vision_url('opencode-go',{'baseUrl':'https://example.invalid/zen/go/v1'}),'https://opencode.ai/inference/go/openai/v1/chat/completions')
 def test_other_provider_unchanged(self):
  self.assertEqual(v._vision_url('other',{'baseUrl':'https://example.invalid/v1/'}),'https://example.invalid/v1/chat/completions')
  with patch.object(v.urllib.request,'urlopen') as opened:v._open_vision(object(),'other',timeout=18);opened.assert_called_once()
 def test_override_strict(self):
  for value in ('https://evil.invalid/v1','https://opencode.ai/zen/v1','https://opencode.ai/inference/go/openai/v1?key=secret','http://opencode.ai/inference/go/openai/v1','https://opencode.ai/inference/go/openai/v1/../v1'):
   with patch.dict('os.environ',{'EPAPER_PHONE_VISION_GO_BASE_URL':value}):
    with self.assertRaises(ValueError):v._vision_url('opencode-go',{'baseUrl':'ignored'})
  with patch.dict('os.environ',{'EPAPER_PHONE_VISION_GO_BASE_URL':'https://opencode.ai/inference/go/openai/v1/'}):self.assertTrue(v._vision_url('opencode-go',{}).endswith('/chat/completions'))
 def test_direct_and_redirect_denied(self):
  with patch.object(v.urllib.request,'build_opener') as built:
   marker=object();v._open_vision(marker,'opencode-go',timeout=18)
   handlers=built.call_args.args
   proxies=[h for h in handlers if isinstance(h,urllib.request.ProxyHandler)]
   self.assertEqual(proxies[0].proxies,{})
   denied=[h for h in handlers if isinstance(h,urllib.request.HTTPRedirectHandler)][0]
   self.assertIsNone(denied.redirect_request(None,None,302,'',{},'https://example.invalid'))
   built.return_value.open.assert_called_once_with(marker,timeout=18)
 def test_success_preserves_full_usage_and_legacy_retry_route(self):
  import json
  usage={'prompt_tokens':10,'completion_tokens':2,'total_tokens':12,'prompt_tokens_details':{'cached_tokens':3},'completion_tokens_details':{'reasoning_tokens':0},'opencode':{'billing_source':'go','tokens':{'input':7,'output':2,'cache_read':3,'cache_write_5m':0,'cache_write_1h':0,'reasoning':0}}}
  cfg={'baseUrl':'https://example.invalid/zen/go/v1'}
  error=v.VisionTransportError('opencode-go','mimo-v2.6-flash',cfg,True)
  with v.same_provider_retry(error),patch.object(v,'_open_vision') as opened:
   opened.return_value.__enter__.return_value.read.return_value=json.dumps({'usage':usage}).encode()
   result,request,provider,_=v.request_vision({'model':'mimo-v2.6-flash'},*v._RETRY_ROUTE.get())
   self.assertEqual(result['usage'],usage)
   self.assertEqual(request.full_url,'https://opencode.ai/inference/go/openai/v1/chat/completions')
   self.assertEqual(provider,'opencode-go');self.assertEqual(opened.call_count,1)
if __name__=='__main__':unittest.main()
