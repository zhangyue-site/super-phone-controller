import hashlib,hmac,unittest
from unittest.mock import patch
from display_service import app_ota,app_screen,firmware
class DualTransportTests(unittest.TestCase):
 def setUp(self):
  self.now=[100.];self.a=app_ota.Authority(lambda:self.now[0]);self.keys={'one':'key','two':'other'}
  self.release=patch.object(firmware,'release',return_value=({'version':'1.6.0','sha256':'a'*64,'size':4096},b'x'*4096));self.release.start();self.addCleanup(self.release.stop)
 def proof(self,nonce):return hmac.new(b'key',b'PCFLASH1\none\n'+bytes.fromhex(nonce),hashlib.sha256).hexdigest()
 def grant(self):
  c=self.a.challenge('one',self.keys);return self.a.authorize('one',c['challenge'],self.proof(c['challenge']),self.keys)['ticket']
 def obj(self):
  n='12'*32;return dict(device='one',boot='aabbccdd',challenge=n,proof=self.proof(n))
 def test_upgrade_exact_signing_and_replay(self):
  t=self.grant();o=self.obj();r=self.a.ble_authorize(t,o,self.keys)
  msg=b'PCOTA-AUTH1\none\naabbccdd\n'+bytes.fromhex(o['challenge'])
  self.assertEqual(r['authorization'],hmac.new(b'key',msg,hashlib.sha256).hexdigest())
  with self.assertRaises(ValueError):self.a.ble_authorize(t,o,self.keys)
 def test_upgrade_denies_bad_proof_wrong_ticket_and_expiry(self):
  t=self.grant();o=self.obj()
  with self.assertRaises(ValueError):self.a.ble_authorize('not-ticket',o,self.keys)
  bad=dict(o,proof='00'*32)
  with self.assertRaises(ValueError):self.a.ble_authorize(t,bad,self.keys)
  bad=dict(o,device='two')
  with self.assertRaises(ValueError):self.a.ble_authorize(t,bad,self.keys)
  self.now[0]+=301
  with self.assertRaises(ValueError):self.a.ble_authorize(t,o,self.keys)
 def usb_obj(self):
  c=app_screen.usb_challenge('one','70041DDBD418',self.keys)
  msg=b'pcusb-v1\none\n70041DDBD418\n'+bytes.fromhex(c['challenge'])
  return dict(device='one',serial='70041DDBD418',challenge=c['challenge'],proof=hmac.new(b'key',msg,hashlib.sha256).hexdigest())
 def test_usb_renew_retains_capture_and_does_not_cancel_task(self):
  with patch.object(app_screen,'AUTHORITY',self.a),patch.object(app_screen,'USB_AUTHORITY',app_ota.Authority(lambda:self.now[0])),patch.object(app_screen.CONVERSATION.mailbox,'cancel',side_effect=AssertionError('must not cancel')):
   self.a.tickets['A'*43]=(150.,'one','old-ble-capture')
   before=set(self.a.tickets);r=app_screen.usb_renew('A'*43,self.usb_obj(),self.keys)
   self.assertEqual(set(self.a.tickets),before);self.assertEqual(self.a.tickets['A'*43],(400.,'one','usb-screen'));self.assertEqual(r['expiresIn'],300)
 def test_usb_renew_cannot_create_session_or_cross_device(self):
  with patch.object(app_screen,'AUTHORITY',self.a),patch.object(app_screen,'USB_AUTHORITY',app_ota.Authority(lambda:self.now[0])):
   self.a.tickets['A'*43]=(150.,'two','usb-screen')
   with self.assertRaises(ValueError):app_screen.usb_renew('A'*43,self.usb_obj(),self.keys)
   with self.assertRaises(ValueError):app_screen.usb_renew('B'*43,self.usb_obj(),self.keys)
 def test_semver_ordering_and_legacy_migration(self):
  self.assertGreater(firmware._release_order('1.6.0'),firmware._release_order('2026.10.28-r3'))
  self.assertGreater(firmware._release_order('1.10.0'),firmware._release_order('1.9.9'))
  self.assertLess(firmware._release_order('1.5.9'),firmware._release_order('1.6.0'))
  for v in ['1.6','01.6.0','1.6.0-unknown','bad']:
   with self.assertRaises(ValueError):firmware._release_order(v)
if __name__=='__main__':unittest.main()
