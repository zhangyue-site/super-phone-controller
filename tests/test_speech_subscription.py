import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from display_service import asr_plan
class SpeechSubscription(unittest.TestCase):
 def test_rejects_paid_and_foreign_routes(self):
  with tempfile.TemporaryDirectory() as d:
   cfg=Path(d)/'cfg.json'
   with patch.dict(os.environ,{'EPAPER_SPEECH_CONFIG':str(cfg)}):
    for url in ('https://api.xiaomimimo.com/v1','https://example.com/v1','http://token-plan-cn.xiaomimimo.com/v1'):
     cfg.write_text(json.dumps(dict(baseUrl=url,apiKey='test')))
     with self.assertRaises(ValueError):asr_plan.load_config()
 def test_existing_plan_route_and_usage_are_preserved(self):
  with tempfile.TemporaryDirectory() as d:
   cfg=Path(d)/'cfg.json';cfg.write_text(json.dumps(dict(baseUrl='https://token-plan-cn.xiaomimimo.com/v1',apiKey='test')))
   wav=Path(d)/'input.wav';wav.write_bytes(b'RIFF'+b'0'*60)
   result={'choices':[{'message':{'content':'连接测试'}}],'usage':{'total_tokens':12}}
   response=MagicMock();response.__enter__.return_value=__import__('io').StringIO(json.dumps(result))
   with patch.dict(os.environ,{'EPAPER_SPEECH_CONFIG':str(cfg)}),patch.object(asr_plan.urllib.request,'urlopen',return_value=response) as call:
    r=asr_plan.transcribe(wav);self.assertEqual(r['usage'],result['usage']);self.assertEqual(r['text'],'连接测试');self.assertEqual(call.call_count,1)
    self.assertIn('token-plan-cn',call.call_args.args[0].full_url)
if __name__=='__main__':unittest.main()
