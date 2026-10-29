"""Host verification of reproducible resources, shared hit geometry and honest UI copy."""
from pathlib import Path
import importlib.util, hashlib, unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('product_gen',ROOT/'tools/generate_product_screens.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class ProductScreens(unittest.TestCase):
 def test_resources_and_geometry(self):
  paths=[mod.MAIN/'product_screens.h',mod.MAIN/'product_ui_layout.h']
  before=[p.read_bytes() for p in paths];groups=mod.generate();self.assertEqual(before,[p.read_bytes() for p in paths])
  self.assertEqual(mod.LAYOUT['consent_begin'],65);self.assertEqual(mod.LAYOUT['consent_end'],125)
  self.assertEqual(mod.LAYOUT['footer_begin'],162);self.assertEqual(mod.LAYOUT['footer_end'],188)
  for frames in groups.values():
   for frame in frames:
    self.assertEqual(frame.size,(200,200));self.assertEqual(frame.mode,'1');self.assertEqual(len(frame.tobytes()),5000)
    # STOP text/target in every key page must have identical pixels.
    self.assertEqual(frame.crop((100,162,200,188)).tobytes(),groups['product_home'][0].crop((100,162,200,188)).tobytes())
  self.assertEqual(len({hashlib.sha256(frame.tobytes()).digest() for frame in groups['product_home']}),8)
 def test_truthful_copy(self):
  homes=''.join(''.join(values) for values in mod.HOMES)
  for forbidden in ('云端在线','已就绪','HID','nonce','transport','IP地址'):self.assertNotIn(forbidden,homes)
  self.assertIn('云端与画面请在手机核对',homes)
  updates=''.join(''.join(values) for values in mod.OTA+mod.BLE)
  self.assertNotIn('升级成功',updates);self.assertIn('启动结果待手机核验',updates)
  power=''.join(''.join(values) for values in mod.POWER)
  self.assertIn('已待机',power);self.assertIn('30秒重启',power);self.assertNotIn('已断电',power)
if __name__=='__main__':unittest.main()
