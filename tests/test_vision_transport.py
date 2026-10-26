import io,json,os,unittest,urllib.error
from unittest.mock import patch
from display_service.general_vision import request_vision

class VisionTransportTests(unittest.TestCase):
 def setUp(self):
  self.cfg={'baseUrl':'https://primary.invalid/v1','apiKey':'synthetic-only'}
  self.backup={'baseUrl':'https://backup.invalid/v1','apiKey':'synthetic-backup','models':[{'id':'mimo-v2.6-flash','input':['text','image']}]}
  self.payload={'model':'mimo-v2.6-flash','messages':[{'role':'user','content':[{'type':'image_url','image_url':{'url':'data:image/jpeg;base64,c3ludGhldGlj'}}]}]}
  self.env=patch.dict(os.environ,{'EPAPER_VISION_FALLBACK_PROVIDER':'opencode-go'},clear=True);self.env.start()
  self.providers=patch('display_service.model_routing.providers',return_value={'opencode-go':self.backup});self.providers.start()
 def tearDown(self):self.providers.stop();self.env.stop()
 def response(self):return io.BytesIO(b'{"choices":[]}')
 def request(self):return request_vision(self.payload,'xiaomi','mimo-v2.6-flash',self.cfg)
 def test_primary_success_never_calls_backup(self):
  with patch('urllib.request.urlopen',return_value=self.response()) as net:
   self.assertEqual(self.request()[2],'xiaomi');self.assertEqual(net.call_count,1)
 def test_timeout_retries_identical_readonly_image_once(self):
  with patch('urllib.request.urlopen',side_effect=[TimeoutError(),self.response()]) as net:
   self.assertEqual(self.request()[2],'opencode-go');self.assertEqual(net.call_count,2)
   a,b=[c.args[0] for c in net.call_args_list];self.assertEqual(a.data,b.data);self.assertEqual(a.get_header('X-opencode-session'),b.get_header('X-opencode-session'))
   self.assertNotEqual(a.full_url,b.full_url)
 def test_429_and_503_may_fallback(self):
  for status in (429,503):
   with self.subTest(status=status),patch('urllib.request.urlopen',side_effect=[urllib.error.HTTPError('synthetic',status,'',{},None),self.response()]) as net:
    self.assertEqual(self.request()[2],'opencode-go');self.assertEqual(net.call_count,2)
 def test_unauthorized_and_invalid_request_never_fallback(self):
  for status in (400,401,403):
   with self.subTest(status=status),patch('urllib.request.urlopen',side_effect=urllib.error.HTTPError('synthetic',status,'',{},None)) as net:
    with self.assertRaisesRegex(ValueError,'视觉'):self.request()
    self.assertEqual(net.call_count,1)
 def test_invalid_json_never_fallback(self):
  with patch('urllib.request.urlopen',return_value=io.BytesIO(b'not json')) as net:
   with self.assertRaises(ValueError):self.request()
   self.assertEqual(net.call_count,1)
 def test_backup_requires_explicit_image_capability(self):
  self.backup['models'][0]['input']=['text']
  with patch('urllib.request.urlopen',side_effect=TimeoutError()) as net:
   with self.assertRaisesRegex(ValueError,'视觉'):self.request()
   self.assertEqual(net.call_count,1)
 def test_both_network_failures_stop_after_two_requests(self):
  with patch('urllib.request.urlopen',side_effect=TimeoutError()) as net:
   with self.assertRaisesRegex(ValueError,'视觉'):self.request()
   self.assertEqual(net.call_count,2)
 def test_backup_is_opt_in_and_mimo_only(self):
  for model,backup in [('deepseek-v4.1-flash','opencode-go'),('mimo-v2.6-flash','')]:
   with self.subTest(model=model),patch.dict(os.environ,{'EPAPER_VISION_FALLBACK_PROVIDER':backup}),patch('urllib.request.urlopen',side_effect=TimeoutError()) as net:
    with self.assertRaises(ValueError):request_vision(self.payload,'xiaomi',model,self.cfg)
    self.assertEqual(net.call_count,1)

 def test_go_primary_can_use_direct_mimo_backup(self):
  with patch.dict(os.environ,{'EPAPER_VISION_FALLBACK_PROVIDER':'xiaomi'}),patch('display_service.model_routing.providers',return_value={'xiaomi':self.backup}),patch('urllib.request.urlopen',side_effect=[TimeoutError(),self.response()]) as net:
   value=request_vision(self.payload,'opencode-go','mimo-v2.6-flash',self.cfg)
   self.assertEqual(value[2],'xiaomi');self.assertEqual(net.call_count,2)
