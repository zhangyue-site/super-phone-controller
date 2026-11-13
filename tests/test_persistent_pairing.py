import tempfile, unittest
from pathlib import Path
from display_service.paired_control import Pairings
class PersistentPairingTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/"pairs.db";self.parents={"p":"device"};self.now=1
  def owner(p):
   if p not in self.parents:raise PermissionError("expired")
   return self.parents[p]
  self.owner=owner
 def tearDown(self):self.tmp.cleanup()
 def new(self):return Pairings(self.owner,clock=lambda:self.now,path=self.path)
 def test_restart_and_parent_replacement(self):
  p=self.new();code=p.issue("p")["code"];self.assertRegex(code,r"^[0-9]{4}$")
  self.assertEqual(p.issue("p")["code"],code);t=p.redeem(code)["ticket"]
  self.parents.clear()
  with self.assertRaises(PermissionError):p.renew(t)
  q=self.new()
  with self.assertRaises(PermissionError):q.redeem(code)
  self.parents["new"]="device";self.assertEqual(q.issue("new")["code"],code)
  self.assertEqual(q.owner(q.redeem(code)["ticket"])[3],"device")
 def test_rotate_revoke_and_rate(self):
  p=self.new();c=p.issue("p")["code"];t=p.redeem(c)["ticket"];p.revoke("p")
  with self.assertRaises(PermissionError):p.owner(t)
  self.assertEqual(p.issue("p")["code"],c)
  new=p.rotate("p")["code"];self.assertNotEqual(new,c)
  for _ in range(10):
   with self.assertRaises(PermissionError):p.redeem("bad",client="test")
  with self.assertRaises(PermissionError):p.redeem(new,client="test")
 def test_unique_across_instances(self):
  p=self.new();q=self.new();a=p.issue("p")["code"];self.parents["q"]="other"
  self.assertNotEqual(a,q.issue("q")["code"])

 def test_cross_instance_revoke_and_concurrent_uniqueness(self):
  import concurrent.futures
  p=self.new();q=self.new();c=p.issue("p")["code"];t=p.redeem(c)["ticket"]
  q.revoke("p")
  with self.assertRaises(PermissionError):p.owner(t)
  def issue(n):
   key="parent"+str(n);self.parents[key]="device"+str(n)
   return self.new().issue(key)["code"]
  with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
   codes=list(pool.map(issue,range(16)))
  self.assertEqual(len(set(codes)),16)
 def test_ticket_is_strong_and_old_parent_is_never_rebound(self):
  p=self.new();code=p.issue("p")["code"];t=p.redeem(code)["ticket"]
  self.assertRegex(t,r"^[A-Za-z0-9_-]{43}$")
  self.parents.pop("p");self.parents["replacement"]="device";p.issue("replacement")
  with self.assertRaises(PermissionError):p.owner(t)
  self.assertEqual(p.owner(p.redeem(code)["ticket"])[3],"device")

 def test_binding_restore_restart_expiry_and_revoke(self):
  p=self.new();code=p.issue("p")["code"];grant=p.redeem(code);binding=grant["bindingToken"]
  self.assertRegex(binding,r"^[A-Za-z0-9_-]{43}$")
  self.now+=301
  with self.assertRaises(PermissionError):p.owner(grant["ticket"])
  restored=p.restore(binding);self.assertEqual(restored["bindingToken"],binding)
  self.assertEqual(p.owner(restored["ticket"])[3],"device")
  q=self.new()
  with self.assertRaises(PermissionError):q.restore(binding)
  q.issue("p");self.assertEqual(q.restore(binding)["bindingToken"],binding)
  raw=self.path.read_bytes();self.assertNotIn(binding.encode(),raw)
  q.revoke("p")
  with self.assertRaises(PermissionError):p.restore(binding)
 def test_rotate_invalidates_persistent_binding(self):
  p=self.new();binding=p.redeem(p.issue("p")["code"])["bindingToken"]
  p.rotate("p")
  with self.assertRaises(PermissionError):p.restore(binding)

 def test_pin_rotation_between_lookup_and_grant_is_rejected(self):
  p=self.new();q=self.new();code=p.issue("p")["code"]
  original=p.parent_device;armed=[True]
  def race(parent):
   if armed[0]:armed[0]=False;q.rotate("p")
   return original(parent)
  p.parent_device=race
  with self.assertRaises(PermissionError):p.redeem(code)
 def test_other_instance_revokes_legacy_before_redemption(self):
  p=self.new();q=self.new();code=p.issue_legacy("p")["code"]
  q.revoke("p")
  with self.assertRaises(PermissionError):p.redeem(code)
 def test_restore_revocation_between_lookup_and_grant_rejected(self):
  p=self.new();q=self.new();binding=p.redeem(p.issue("p")["code"])["bindingToken"]
  original=p.parent_device;armed=[True]
  def race(parent):
   if armed[0]:armed[0]=False;q.revoke("p")
   return original(parent)
  p.parent_device=race
  with self.assertRaises(PermissionError):p.restore(binding)

 def test_renew_revoked_between_owner_and_extension_rejected(self):
  p=self.new();q=self.new();ticket=p.redeem(p.issue("p")["code"])["ticket"]
  original=p.parent_device;armed=[True]
  def race(parent):
   if armed[0]:armed[0]=False;q.revoke("p")
   return original(parent)
  p.parent_device=race
  with self.assertRaises(PermissionError):p.renew(ticket)

 def test_attach_after_restart_restores_without_creating_or_changing_code(self):
  p=self.new();code=p.issue("p")["code"];binding=p.redeem(code)["bindingToken"]
  q=self.new();q.attach("p")
  self.assertEqual(q.restore(binding)["device"],"device")
  self.assertEqual(q.issue("p")["code"],code)
  self.assertEqual(q.db.execute("SELECT count(*) FROM pairings").fetchone()[0],1)
  self.parents["new-device-parent"]="unpaired"
  q.attach("new-device-parent")
  self.assertEqual(q.db.execute("SELECT count(*) FROM pairings").fetchone()[0],1)
