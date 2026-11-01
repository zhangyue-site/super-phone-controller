import hashlib,hmac,unittest
from unittest.mock import patch
from display_service.app_ota import Authority

class ControlIdentityScopeTests(unittest.TestCase):
 def setUp(self):
  self.now=100.
  self.auth=Authority(clock=lambda:self.now,firmware_scope=False)
  self.keys={'amoled-test':'synthetic-test-key'}
 def challenge(self):
  return self.auth.challenge('amoled-test',self.keys)
 def proof(self,c):
  return hmac.new(self.keys[c['device']].encode(),b'PCFLASH1\n'+c['device'].encode()+b'\n'+bytes.fromhex(c['challenge']),hashlib.sha256).hexdigest()
 def grant(self,c):
  return self.auth.authorize(c['device'],c['challenge'],self.proof(c),self.keys)
 def test_control_without_any_firmware_release(self):
  with patch('display_service.firmware.release',side_effect=FileNotFoundError) as release:
   c=self.challenge();g=self.grant(c)
   self.assertEqual(set(g),{'ticket','expiresIn'})
   self.assertEqual(self.auth.tickets[g['ticket']][1],'amoled-test')
   release.assert_not_called()
   with self.assertRaises(ValueError):self.grant(c)
 def test_control_ticket_never_downloads_firmware(self):
  g=self.grant(self.challenge())
  with patch('display_service.firmware.release') as release:
   with self.assertRaises(ValueError):self.auth.image(g['ticket'])
   release.assert_not_called()
 def test_expired_or_wrong_proof_and_unknown_device(self):
  c=self.challenge()
  with self.assertRaises(ValueError):self.auth.authorize(c['device'],c['challenge'],'0'*64,self.keys)
  c=self.challenge();self.now+=121
  with self.assertRaises(ValueError):self.grant(c)
  with self.assertRaises(ValueError):self.auth.challenge('missing',self.keys)
 def test_firmware_authority_still_requires_real_release(self):
  auth=Authority();c=auth.challenge('amoled-test',self.keys)
  with patch('display_service.firmware.release',side_effect=FileNotFoundError):
   with self.assertRaises(FileNotFoundError):auth.authorize(c['device'],c['challenge'],self.proof(c),self.keys)
