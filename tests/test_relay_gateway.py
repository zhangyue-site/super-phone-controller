import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from display_service.dialogue import Mailbox
from display_service.remote_control import RemoteControl
from display_service.relay_http import Gateway
from display_service.hid_relay import Relay
from test_hid_relay import KEY,NONCE,receipt

class GatewayTests(unittest.TestCase):
 def test_idle_armed_poll_does_not_starve_later_task(self):
  with tempfile.TemporaryDirectory() as tmp:
   box=Mailbox()
   c=SimpleNamespace(mailbox=box,start=lambda d,s,q,text:box.create(d,s,q))
   remote=RemoteControl(c,Path(tmp)/'task.json',screen_ready=lambda d:True)
   remote.binding_allowed=lambda o:True
   relay=Relay(Path(tmp)/'relay.db',lambda d:KEY)
   g=Gateway(relay,remote)
   try:
    g.attach('epaper-01','owner',receipt())
    relay.offer('epaper-01',6,[0]*5)
    arm=relay.poll('epaper-01','owner',NONCE)
    g.ack('epaper-01','owner',NONCE,arm['id'],receipt(1,6,7,1))
    for _ in range(4):g.poll('epaper-01','owner',NONCE)
    owner=('android-app','owner','owner','epaper-01')
    task=remote.prepare(owner,'打开设置');remote.confirm(owner,task['task_id'])
    for _ in range(4):g.poll('epaper-01','owner',NONCE)
    self.assertEqual(remote.status(owner,task['task_id'])['state'],'running')
   finally:relay.close()
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

 def test_verified_completion_disarms_and_accepts_next_task_without_reattach(self):
  with tempfile.TemporaryDirectory() as tmp:
   box=Mailbox();c=SimpleNamespace(mailbox=box,start=lambda d,s,q,text:box.create(d,s,q))
   remote=RemoteControl(c,Path(tmp)/'task.json',screen_ready=lambda d:True)
   remote.binding_allowed=lambda o:True
   relay=Relay(Path(tmp)/'relay.db',lambda d:KEY);g=Gateway(relay,remote)
   owner=('android-app','owner','owner','epaper-01')
   try:
    g.attach('epaper-01','owner',receipt())
    task=remote.prepare(owner,'打开设置');remote.confirm(owner,task['task_id'])
    arm=g.poll('epaper-01','owner',NONCE);self.assertEqual(arm['op'],6)
    g.ack('epaper-01','owner',NONCE,arm['id'],receipt(arm['seq'],6,7,1))
    for _ in range(4):g.poll('epaper-01','owner',NONCE)
    turn=g.turns['epaper-01'];old_sequence=turn['sequence'];old_lease=turn['lease'];old_session=turn['session']
    j=box.jobs['epaper-01'];j.navigation_verified=True;j.state='done';j.done=True
    disarm=g.poll('epaper-01','owner',NONCE);self.assertEqual(disarm['op'],7)
    # An unsettled USB mode cannot clear the current job or arm a later task.
    with self.assertRaises(ValueError):g.ack('epaper-01','owner',NONCE,disarm['id'],receipt(disarm['seq'],7,8,1))
    self.assertIsNotNone(g.turns['epaper-01']['job'])
    g.ack('epaper-01','owner',NONCE,disarm['id'],receipt(disarm['seq'],7,8,0))
    self.assertEqual(g.poll('epaper-01','owner',NONCE)['state'],'idle')
    self.assertEqual((turn['session'],turn['lease']),(old_session,old_lease))
    self.assertIsNone(turn['job']);self.assertGreater(turn['sequence'],old_sequence)
    next_task=remote.prepare(owner,'打开设置');remote.confirm(owner,next_task['task_id'])
    arm2=g.poll('epaper-01','owner',NONCE);self.assertEqual(arm2['op'],6)
    self.assertGreater(arm2['seq'],disarm['seq'])
    g.ack('epaper-01','owner',NONCE,arm2['id'],receipt(arm2['seq'],6,7,1))
    for _ in range(4):g.poll('epaper-01','owner',NONCE)
    self.assertEqual(remote.status(owner,next_task['task_id'])['state'],'running')
    self.assertGreater(remote.records[next_task['task_id']]['sequence'],old_sequence)
    failed=box.jobs['epaper-01'];failed.state='error';failed.done=True
    stop=g.poll('epaper-01','owner',NONCE);self.assertEqual(stop['op'],5)
    g.ack('epaper-01','owner',NONCE,stop['id'],receipt(stop['seq'],5,5,0))
    self.assertNotIn('epaper-01',g.turns)

   finally:relay.close()
