"""Public-source configuration checks; no private config or hardware required."""
from pathlib import Path
import re
import unittest
ROOT=Path(__file__).resolve().parents[1]
MAIN=ROOT/'firmware-epaper/main'
class PublicFirmwareConfig(unittest.TestCase):
 def test_maintenance_defaults_closed(self):
  config=(MAIN/'Kconfig.projbuild').read_text()
  for name in ('CONTROLLER_USB_MAINTENANCE','CONTROLLER_ADB_MAINTENANCE'):
   block=config.split('config '+name,1)[1].split('config ',1)[0];self.assertIn('default n',block)
  cmake=(MAIN/'CMakeLists.txt').read_text();self.assertNotIn('CONTROLLER_USB_MAINTENANCE=1',cmake)
  self.assertIn('$<BOOL:${CONFIG_CONTROLLER_USB_MAINTENANCE}>',cmake)
 def test_identity_proof_stays_outside_maintenance_gate(self):
  source=(MAIN/'main.cpp').read_text()
  proof=source.index('static bool usb_proof_command(')
  maintenance=source.index('#if CONTROLLER_USB_MAINTENANCE\nstatic void console_maintenance_command(')
  dispatch=source.index('static void console_command(')
  self.assertLess(proof,maintenance);self.assertGreater(dispatch,maintenance)
  self.assertIn('usb_console_dispatch(line,CONTROLLER_USB_MAINTENANCE',source)
  self.assertIn('controller_device_sign(domain,nonce,proof)',source)
 def test_tls_uses_configured_identity_and_bundle(self):
  for name in ('main.cpp','dialogue.cpp','ota.cpp'):
   source=(MAIN/name).read_text();self.assertIn('cloud_tls_configure(cfg)',source);self.assertIn('esp_crt_bundle_attach',source)
   self.assertNotRegex(source,r'cfg\.common_name\s*=\s*"')
   self.assertNotRegex(source,r'set_header\([^\n]+,"Host","')
  policy=(MAIN/'cloud_http_config.h').read_text();self.assertIn('skip_cert_common_name_check=false',policy)
 def test_no_private_files_are_part_of_test_fixture(self):
  self.assertFalse((ROOT/'tests/fixtures/adb_disabled/device_config.h').exists())
  example=(MAIN/'device_config.example.h').read_text();self.assertIn('controller.example.invalid',example)
if __name__=='__main__':unittest.main()
