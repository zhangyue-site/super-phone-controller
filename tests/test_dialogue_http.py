import http.client,json,tempfile,threading,unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from display_service import app
from display_service.conversation import Conversation
from display_service.dialogue import Mailbox
class HttpTests(unittest.TestCase):
 def test_authenticated_turn_and_cross_device_isolation(self):
  with tempfile.TemporaryDirectory() as temp:
   config=Path(temp)/'devices.json';config.write_text(json.dumps({'one':'token1','two':'token2'}))
   c=Conversation(Mailbox(),lambda m:{'action':'reply','reply':'测试回答'},lambda t:b'\0\1'*100,lambda *a,**kw:None)
   server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
   def post(path,token='token1',body=None):
    conn=http.client.HTTPConnection(*server.server_address);headers={'Authorization':'Bearer '+token,'X-Voice-Session':'a'*16,'X-Voice-Sequence':'1'}
    conn.request('POST',path,json.dumps(body).encode() if body else b'',headers);r=conn.getresponse();result=(r.status,r.read());conn.close();return result
   try:
    with patch.object(app,'CONFIG',config),patch.object(app,'CONVERSATION',c):
     self.assertEqual(post('/dialogue/text',token='bad',body={'text':'你好'})[0],401)
     self.assertEqual(post('/dialogue/text',body={'text':'你好'})[0],200)
     self.assertEqual(post('/dialogue/poll',token='token2')[0],409)
     self.assertEqual(post('/dialogue/audio')[1],b'\0\1'*100)
     self.assertEqual(post('/dialogue/text',body={'text':'你好'})[0],409)
     with patch.object(app,'write_interaction',lambda *a:None):self.assertEqual(post('/stop')[0],200)
     self.assertEqual(post('/dialogue/audio')[0],409)
   finally:server.shutdown();server.server_close();thread.join()
 def test_voice_dialogue_upload_returns_without_locking(self):
  import array
  with tempfile.TemporaryDirectory() as temp:
   config=Path(temp)/'devices.json';config.write_text(json.dumps({'one':'token1'}))
   c=Conversation(Mailbox(),lambda m:{'action':'reply','reply':'收到语音'},lambda t:b'\1\0'*100,lambda *a,**kw:None)
   server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
   try:
    with patch.object(app,'CONFIG',config),patch.object(app,'CONVERSATION',c),patch.object(app,'recognize',lambda r:'你好'),patch.object(app,'write_interaction',lambda *a:None):
     conn=http.client.HTTPConnection(*server.server_address,timeout=2)
     conn.request('POST','/voice',array.array('h',[600,-600]*4000).tobytes(),{'Authorization':'Bearer token1','X-Voice-Session':'c'*16,'X-Voice-Sequence':'1','X-Voice-Dialogue':'1'})
     response=conn.getresponse();self.assertEqual(response.status,200);response.read();conn.close()
     self.assertIn('one',c.mailbox.jobs)
   finally:server.shutdown();server.server_close()
