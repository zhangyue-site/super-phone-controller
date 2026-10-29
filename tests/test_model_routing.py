import io,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from display_service import wechat_vision,general_vision,conversation
from test_wechat_nav import frame

class ModelRoutingTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'models.json'
  self.path.write_text(json.dumps({'models':{'providers':{'opencode-go':{'baseUrl':'https://models.invalid/v1','apiKey':'synthetic-only','models':[{'id':'mimo-v2.6-flash'},{'id':'deepseek-v4.1-flash'},{'id':'glm-5.3-flash'}]}}}}))
  self.env=patch.dict(os.environ,{'EPAPER_MODEL_CONFIG':str(self.path)},clear=True);self.env.start()
 def tearDown(self):self.env.stop();self.tmp.cleanup()
 def response(self,value):return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}]}).encode())
 def test_current_provider_supports_both_vision_paths_without_old_alias(self):
  for module in (wechat_vision,general_vision):
   with self.subTest(module=module.__name__),patch('display_service.general_vision._open_vision' if module is general_vision else 'urllib.request.urlopen',return_value=self.response({'screen':'unknown','coordinate_system':'pixels'})) as net:
    self.assertEqual(module.observe(frame(0),'test')['screen'],'unknown')
    request=net.call_args.args[0]
    self.assertEqual(json.loads(request.data)['model'],'mimo-v2.6-flash')
    self.assertEqual(request.get_header('User-agent'),'phone-controller/1.0')
    self.assertTrue(request.get_header('X-opencode-session'))
 def test_pinned_unknown_provider_fails_without_sending_to_other_provider(self):
  with patch.dict(os.environ,{'EPAPER_VISION_PROVIDER':'missing'}),patch('urllib.request.urlopen') as net:
   with self.assertRaisesRegex(ValueError,'configured'):wechat_vision.observe(b'synthetic','test')
   net.assert_not_called()
 def test_text_uses_configured_model_id_after_provider_migration(self):
  with patch('urllib.request.urlopen',return_value=self.response({'action':'reply','reply':'ok'})) as net:
   self.assertEqual(conversation.decide([{'role':'user','content':'test'}])['reply'],'ok')
   self.assertEqual(json.loads(net.call_args.args[0].data)['model'],'deepseek-v4.1-flash')
 def test_json_mode_has_explicit_instruction_without_mutating_history(self):
  messages=[{'role':'system','content':'Original instructions'},{'role':'user','content':'hello'}]
  with patch('urllib.request.urlopen',return_value=self.response({'action':'reply','reply':'ok'})) as net:
   conversation.decide(messages)
   sent=json.loads(net.call_args.args[0].data)
   self.assertIn('json',str(sent['messages']).lower())
   self.assertEqual(messages[0]['content'],'Original instructions')
 def test_thinking_only_fallback_does_not_disable_thinking(self):
  with patch('urllib.request.urlopen',side_effect=[OSError('primary unavailable'),self.response({'action':'reply','reply':'ok'})]) as net:
   conversation.decide([{'role':'user','content':'test'}])
   sent=json.loads(net.call_args.args[0].data)
   self.assertEqual(sent['model'],'glm-5.3-flash')
   self.assertNotEqual(sent.get('thinking'),{'type':'disabled'})
   self.assertGreaterEqual(sent['max_tokens'],2048)
 def test_task_scope_reuses_header_and_separates_tasks_without_raw_identity(self):
  from display_service.model_routing import task_scope,request_headers
  with task_scope('private-device','private-session',1):
   a=request_headers({'apiKey':'test'})['x-opencode-session']
   self.assertEqual(a,request_headers({'apiKey':'test'})['x-opencode-session'])
  with task_scope('private-device','private-session',2):
   b=request_headers({'apiKey':'test'})['x-opencode-session']
  self.assertNotEqual(a,b);self.assertNotIn('private',a)
if __name__=='__main__':unittest.main()
