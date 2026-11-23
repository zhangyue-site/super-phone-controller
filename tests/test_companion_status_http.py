import os,unittest,tempfile,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from display_service.remote_control import RemoteControl
from display_service.dialogue import Mailbox
from display_service import remote_http
class Handler:
 path='/board-companion';command='GET'
 def __init__(self,device):self.identity=device;self.response=None
 def device(self):return self.identity
 def reply(self,code,body):self.response=(code,json.loads(body))
class StatusHttp(unittest.TestCase):
 def test_device_scope_auth_and_read_only_method(self):
  with tempfile.TemporaryDirectory() as tmp:
   remote=RemoteControl(SimpleNamespace(mailbox=Mailbox()),path=Path(tmp)/'tasks.json')
   for ident,device,reply in [('a'*32,'board-a','own result'),('b'*32,'board-b','other private result')]:
    remote.records[ident]={'owner':['telegram','sender','conversation',device],'state':'done','reply':reply,'verified':True}
   before=json.dumps(remote.records,sort_keys=True)
   with patch.object(remote_http,'REMOTE',remote),patch.dict(os.environ,EPAPER_REMOTE_CONTROL='1'):
    h=Handler(None);self.assertTrue(remote_http.handle(h,None));self.assertEqual(h.response[0],403)
    h=Handler('board-a');self.assertTrue(remote_http.handle(h,None));self.assertEqual(h.response[1]['task_id'],'a'*32)
    self.assertNotIn('other private',json.dumps(h.response));self.assertNotIn('owner',h.response[1])
    h.command='POST';self.assertTrue(remote_http.handle(h,None));self.assertEqual(h.response[0],405)
   self.assertEqual(json.dumps(remote.records,sort_keys=True),before);self.assertEqual(remote.c.mailbox.jobs,{})
if __name__=='__main__':unittest.main()
