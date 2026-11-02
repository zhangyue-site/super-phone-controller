import hashlib,hmac,json,os,struct,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from display_service import firmware,app_ota
from test_firmware_publish import image
class AmoledFirmwareTests(unittest.TestCase):
 def test_explicit_private_target_registry_rejects_cross_board(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);registry=root/'targets.json';registry.write_text(json.dumps({'test-board':'phone_controller_amoled'}))
   with patch.dict(os.environ,CONTROLLER_FIRMWARE_TARGETS=str(registry)),patch.object(firmware,'ROOT',root/'releases'):
    blob=image('0.3.0-amoled','phone_controller_amoled');entry=firmware.publish('test-board',blob,'a'*40)
    self.assertEqual(firmware.release('test-board',entry['sha256'])[1],blob)
    for device,bad in [('legacy',blob),('test-board',image())]:
     with self.assertRaises(ValueError):firmware.publish(device,bad,'b'*40)
 def test_image_bound_authorization_contains_exact_version_size_and_digest(self):
  entry={'size':5000,'version':'0.3.0-amoled','sha256':'a'*64}
  auth=app_ota.Authority();now=auth.clock();auth.tickets['t'*43]=(now+300,'test-board','a'*64)
  nonce='b'*64;boot='c'*32;key='test-secret';obj={'device':'test-board','boot':boot,'challenge':nonce,'proof':hmac.new(key.encode(),b'PCFLASH1\ntest-board\n'+bytes.fromhex(nonce),hashlib.sha256).hexdigest()}
  with patch.object(firmware,'release',return_value=(entry,b'x'*5000)),patch.object(firmware,'target_profile',return_value=('phone_controller_amoled',0x600000)):
   result=auth.ble_authorize('t'*43,obj,{'test-board':key})
  raw=bytes.fromhex(result['authorization']);self.assertEqual(len(raw),100)
  self.assertEqual(raw[:32],b'0.3.0-amoled'.ljust(32,b'\0'));self.assertEqual(raw[32:64],bytes.fromhex('a'*64));self.assertEqual(struct.unpack('<I',raw[64:68])[0],5000)
  msg=b'PCOTA-AUTH2\ntest-board\n'+boot.encode()+b'\nphone_controller_amoled\n0.3.0-amoled\n'+bytes.fromhex(nonce)+raw[32:68]
  self.assertEqual(raw[68:],hmac.new(key.encode(),msg,hashlib.sha256).digest())
  self.assertEqual(result['protocol'],'hmac-sha256-image-v2')
 def test_registry_failure_never_silently_defaults_target(self):
  with patch.dict(os.environ,CONTROLLER_FIRMWARE_TARGETS='/nonexistent/private-registry.json'):
   with self.assertRaises(OSError):firmware.target_profile('test-board')
if __name__=='__main__':unittest.main()
