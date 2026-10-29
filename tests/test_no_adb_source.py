from pathlib import Path
import unittest,re
ROOT=Path(__file__).resolve().parents[1]
MAIN=ROOT/'firmware-epaper/main'
class NoAdb(unittest.TestCase):
 def test_default_disabled(self):
  config=(MAIN/'Kconfig.projbuild').read_text().split('config CONTROLLER_ADB_MAINTENANCE',1)[1].split('config ',1)[0]
  self.assertIn('default n',config)
  generated=ROOT/'firmware-epaper/sdkconfig.usb-local'
  if generated.exists():self.assertIn('# CONFIG_CONTROLLER_ADB_MAINTENANCE is not set',generated.read_text())
 def test_no_production_start_or_fallback(self):
  source=(MAIN/'main.cpp').read_text()
  self.assertRegex(source,r'#if CONFIG_CONTROLLER_USB_LOCAL && CONFIG_CONTROLLER_ADB_MAINTENANCE\s+controller_adb_init\(\);\s+#endif')
  self.assertIn('product_offline[0]',source)
  self.assertRegex(source,r'#if CONFIG_CONTROLLER_ADB_MAINTENANCE\s+int adb_error=controller_adb_error')
  self.assertIn('X-HID-Keyboard', (MAIN/'dialogue.cpp').read_text())
  adb=(MAIN/'adb_local.cpp').read_text();self.assertIn('#if CONFIG_CONTROLLER_USB_LOCAL && CONFIG_CONTROLLER_ADB_MAINTENANCE',adb)
  dialogue=(MAIN/'dialogue.cpp').read_text();self.assertIn('Legacy type_text is never a production fallback',dialogue)
 def test_wifi_first(self):
  ota=(MAIN/'ota.cpp').read_text();self.assertIn('cloud_transport_ready(controller_voice_direct_network()',ota)
  self.assertIn('WiFi unavailable; use BLE upgrade, no ADB fallback',ota)
  self.assertIn('Boot report deferred: WiFi unavailable',ota)
if __name__=='__main__':unittest.main()
