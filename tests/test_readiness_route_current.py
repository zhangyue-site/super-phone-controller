import io,json,sys,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from display_service import readiness,events,control
class Routes(unittest.TestCase):
 def test_current_configured_route(self):
  routes=[('current','current-model',{'baseUrl':'https://example.invalid/custom/v1','apiKey':'test'})]
  with patch('display_service.model_routing.chat_routes',return_value=routes),patch('display_service.model_routing.request_headers',return_value={'Authorization':'Bearer test'}),patch('display_service.readiness.urllib.request.urlopen',return_value=io.BytesIO(b'{"choices":[{"message":{"content":"OK"}}]}')) as request:
   readiness.chat_probe()
  req=request.call_args.args[0]
  self.assertEqual(req.full_url,'https://example.invalid/custom/v1/chat/completions')
  self.assertEqual(json.loads(req.data)['model'],'current-model')
 def test_failed_route_not_ready(self):
  with patch('display_service.model_routing.chat_routes',return_value=[]):
   with self.assertRaises(RuntimeError):readiness.chat_probe()
 def test_numeric_touch_rejection_event(self):
  with tempfile.TemporaryDirectory() as root,patch.object(control,'ROOT',Path(root)):
   raw=json.dumps(dict(boot=1,seq=1,ms=10,event='touch_reject',page=5,a=2,b=3,result=0)).encode()
   self.assertEqual(events.ingest('test-device',raw),1)
if __name__=='__main__':unittest.main()
