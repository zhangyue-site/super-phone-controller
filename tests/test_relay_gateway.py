import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from display_service.dialogue import Mailbox
from display_service.remote_control import RemoteControl
from display_service.relay_http import Gateway
from display_service.hid_relay import Relay
from test_hid_relay import KEY,NONCE,receipt

class GatewayTests(unittest.TestCase):
 def test_cloud_confirm_arm_mailbox_receipt_and_stop(self):
  with tempfile.TemporaryDirectory() as tmp:
   box=Mailbox()
   c=SimpleNamespace(mailbox=box,start=lambda d,s,q,text:box.create(d,s,q))
   remote=RemoteControl(c,Path(tmp)/"task.json",screen_ready=lambda d:True)
   remote.binding_allowed=lambda o:True
   relay=Relay(Path(tmp)/"relay.db",lambda d:KEY)
   g=Gateway(relay,remote)
   try:
    g.attach("epaper-01","owner",receipt())
    self.assertEqual(g.poll("epaper-01","owner",NONCE)["state"],"idle")
    owner=("android-app","owner","owner","epaper-01")
    task=remote.prepare(owner,"打开设置");remote.confirm(owner,task["task_id"])
    arm=g.poll("epaper-01","owner",NONCE);self.assertEqual(arm["op"],6)
    g.ack("epaper-01","owner",NONCE,arm["id"],receipt(1,6,7,1))
    g.poll("epaper-01","owner",NONCE)
    g.poll("epaper-01","owner",NONCE)
    j=box.jobs["epaper-01"];box.offer(j,{"op":"hid_home"})
    action=g.poll("epaper-01","owner",NONCE);self.assertEqual(action["op"],1)
    g.ack("epaper-01","owner",NONCE,action["id"],receipt(2,1,3,1))
    self.assertEqual(j.result,(True,"HID_HOME_REPORT_SENT",""))
    self.assertFalse(remote.status(owner,task["task_id"])["verified"])
    remote.stop(owner)
    stop=g.poll("epaper-01","owner",NONCE);self.assertEqual(stop["op"],5)
    g.ack("epaper-01","owner",NONCE,stop["id"],receipt(3,5,5,0))
    self.assertNotIn("epaper-01",g.turns)
   finally:relay.close()
