import unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
from display_service.remote_control import RemoteControl
from display_service.dialogue import Mailbox
class DeviceStatusTests(unittest.TestCase):
 def test_device_isolation_and_active_priority(self):
  with tempfile.TemporaryDirectory() as d:
   remote=RemoteControl(SimpleNamespace(mailbox=Mailbox()),Path(d)/'state.json')
   remote.records={'a'*32:{'owner':['android-app','u','c','board'],'state':'queued','reply':'queued','verified':False,'expires':remote.clock()+60},'b'*32:{'owner':['android-app','x','c','other'],'state':'done','reply':'private','verified':True},'c'*32:{'owner':['android-app','u','c','board'],'state':'done','reply':'old','verified':True}}
   self.assertEqual(remote.companion_status('board')['task_id'],'a'*32)
   self.assertEqual(remote.companion_status('empty')['state'],'idle')
   self.assertNotIn('owner',remote.companion_status('board'))
if __name__=='__main__':unittest.main()
