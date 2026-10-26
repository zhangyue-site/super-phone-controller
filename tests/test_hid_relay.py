import hashlib,hmac,json,struct,tempfile,unittest
from pathlib import Path
from display_service.hid_relay import Relay

KEY=b"test-only-device-key"
NONCE="12"*16
def receipt(seq=0,op=0,result=0,hid=0,ready=1):
 d=dict(nonce=NONCE,seq=seq,op=op,result=result,hid=hid,busy=0,ready=ready)
 s="PCBLE1-ACK\n%s\n%d\n%d\n%d\n%d\n%d\n%d"%(NONCE,seq,op,result,hid,0,ready)
 k=hmac.new(KEY,("PCBLE1\nepaper-01\n"+NONCE).encode(),hashlib.sha256).digest()
 d["proof"]=hmac.new(k,s.encode(),hashlib.sha256).hexdigest()
 return d
class RelayTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/"relay.db"
  self.now=1.;self.r=Relay(self.path,lambda d:KEY,clock=lambda:self.now)
 def tearDown(self):self.r.close();self.tmp.cleanup()
 def test_prearmed_connection_only_disarms_before_control(self):
  self.r.attach("epaper-01","owner",receipt(hid=1))
  p=self.r.poll("epaper-01","owner",NONCE)
  self.assertEqual((p["seq"],p["op"]),(1,7))
  with self.assertRaises(ValueError):self.r.offer("epaper-01",1,[0]*5)
  with self.assertRaises(ValueError):self.r.ack("epaper-01","owner",NONCE,p["id"],receipt(1,7,8,1))
  self.r.ack("epaper-01","owner",NONCE,p["id"],receipt(1,7,8,0))
  with self.assertRaises(ValueError):self.r.offer("epaper-01",1,[0]*5)
  self.r.offer("epaper-01",6,[0]*5)
  self.assertEqual(self.r.poll("epaper-01","owner",NONCE)["op"],6)
 def test_unsettled_initial_connection_refused(self):
  with self.assertRaises(PermissionError):self.r.attach("epaper-01","owner",receipt(ready=0))
 def test_proof_required_and_single_owner(self):
  bad=receipt();bad["proof"]="00"*32
  with self.assertRaises(PermissionError):self.r.attach("epaper-01","owner",bad)
  self.r.attach("epaper-01","owner",receipt())
  with self.assertRaises(PermissionError):self.r.poll("epaper-01","other",NONCE)
 def test_packet_is_signed_and_never_reissued(self):
  self.r.attach("epaper-01","owner",receipt());i=self.r.offer("epaper-01",6,[0]*5)
  p=self.r.poll("epaper-01","owner",NONCE)
  self.assertEqual(p["id"],i);self.assertEqual(bytes.fromhex(p["packet"])[:16],struct.pack("<BBI5H",1,6,1,*([0]*5)))
  self.assertEqual(self.r.poll("epaper-01","owner",NONCE)["state"],"awaiting_receipt")
  self.r.ack("epaper-01","owner",NONCE,i,receipt(1,6,7,1))
  self.assertEqual(self.r.status(i)["state"],"acknowledged")
 def test_ack_requires_same_action_and_usb_ready(self):
  self.r.attach("epaper-01","owner",receipt());i=self.r.offer("epaper-01",6,[0]*5);self.r.poll("epaper-01","owner",NONCE)
  for r in (receipt(2,6,7,1),receipt(1,1,7,1),receipt(1,6,7,1,0)):
   with self.assertRaises(ValueError):self.r.ack("epaper-01","owner",NONCE,i,r)
  self.assertEqual(self.r.status(i)["state"],"issued")
 def test_uncertain_restart_cannot_repeat(self):
  self.r.attach("epaper-01","owner",receipt());i=self.r.offer("epaper-01",6,[0]*5);self.r.poll("epaper-01","owner",NONCE)
  self.r.close();self.r=Relay(self.path,lambda d:KEY,clock=lambda:self.now)
  self.assertEqual(self.r.status(i)["state"],"uncertain")
  with self.assertRaises(PermissionError):self.r.poll("epaper-01","owner",NONCE)
 def test_rejected_board_ack_is_not_success(self):
  self.r.attach("epaper-01","owner",receipt());i=self.r.offer("epaper-01",6,[0]*5);self.r.poll("epaper-01","owner",NONCE)
  self.r.ack("epaper-01","owner",NONCE,i,receipt(1,6,4))
  self.assertEqual(self.r.status(i)["state"],"failed")
  with self.assertRaises(PermissionError):self.r.offer("epaper-01",1,[0]*5)
 def test_timeout_requires_reconciliation(self):
  self.r.attach("epaper-01","owner",receipt());i=self.r.offer("epaper-01",6,[0]*5);self.r.poll("epaper-01","owner",NONCE)
  self.now+=16
  with self.assertRaises(PermissionError):self.r.poll("epaper-01","owner",NONCE)
  self.assertEqual(self.r.status(i)["state"],"uncertain")
 def test_invalid_parameters_do_not_consume(self):
  self.r.attach("epaper-01","owner",receipt())
  for op,a in ((3,[65535,1,0,0,0]),(4,[1,2,3,4,20]),(1,[1,0,0,0,0]),(True,[0]*5)):
   with self.assertRaises(ValueError):self.r.offer("epaper-01",op,a)
  i=self.r.offer("epaper-01",6,[0]*5);self.assertEqual(self.r.poll("epaper-01","owner",NONCE)["seq"],1)
 def test_retired_nonce_cannot_be_attached_after_restart(self):
  self.r.attach("epaper-01","owner",receipt())
  self.r.detach("epaper-01","owner",NONCE)
  self.r.close();self.r=Relay(self.path,lambda d:KEY,clock=lambda:self.now)
  with self.assertRaises(PermissionError):self.r.attach("epaper-01","owner",receipt())
 def test_malformed_initial_receipt_is_rejected(self):
  with self.assertRaises(PermissionError):self.r.attach("epaper-01","owner",[])
 def test_nonzero_start_sequence_is_refused(self):
  with self.assertRaises(PermissionError):self.r.attach("epaper-01","owner",receipt(4,1,3,1))
if __name__=="__main__":unittest.main()
