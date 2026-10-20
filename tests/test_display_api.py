import http.client,json,tempfile,threading,unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from display_service import app,control

class DisplayApiTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory()
  root=Path(cls.tmp.name)
  cls.old=(app.CONFIG,app.QUOTAS,control.ROOT)
  app.CONFIG=root/'devices.json';app.QUOTAS=root/'quota';control.ROOT=root/'state'
  app.QUOTAS.mkdir()
  app.CONFIG.write_text(json.dumps({'phone-a':'a'*64,'phone-b':'b'*64}))
  cls.server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
  cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
 @classmethod
 def tearDownClass(cls):
  cls.server.shutdown();cls.server.server_close();cls.thread.join()
  app.CONFIG,app.QUOTAS,control.ROOT=cls.old
  cls.tmp.cleanup()
 def request(self,path,token=None,method='GET'):
  c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
  c.request(method,path,headers={'Authorization':'Bearer '+token} if token else {})
  r=c.getresponse();result=(r.status,r.read());c.close();return result
 def test_anonymous_and_wrong_token_rejected(self):
  self.assertEqual(self.request('/status')[0],401)
  self.assertEqual(self.request('/status','incorrect')[0],401)
 def test_server_originated_state_isolated_by_device(self):
  control.write('phone-a','waiting','等待手机连接')
  a=json.loads(self.request('/status','a'*64)[1])
  b=json.loads(self.request('/status','b'*64)[1])
  self.assertEqual(a['interaction']['task'],'等待手机连接')
  self.assertNotIn('task',b['interaction'])
 def test_stop_does_not_claim_actuator_execution(self):
  status,raw=self.request('/stop','b'*64,'POST')
  self.assertEqual(status,200)
  self.assertEqual(json.loads(raw),{'recorded':True,'actuatorConnected':False})
 def test_fixed_size_monochrome_frame(self):
  status,raw=self.request('/screen.bin','a'*64)
  self.assertEqual(status,200)
  self.assertEqual(len(raw),5000)
 def test_arbitrary_file_routes_not_available(self):
  self.assertEqual(self.request('/../../etc/phone-controller/devices.example.json','a'*64)[0],404)
