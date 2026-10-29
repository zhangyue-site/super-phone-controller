"""Offline signer-config tests. Never import Bluetooth or contact a signer/device."""
import ast
import contextlib
import hashlib
import hmac
import io
import json
from pathlib import Path
import tempfile
import unittest
import unittest.mock

SOURCE=Path(__file__).with_name('ble_direct_client.py')
TREE=ast.parse(SOURCE.read_text())
SIGNER=next(ast.literal_eval(node.value) for node in TREE.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SIGNER_CODE' for t in node.targets))

class SignerConfigTests(unittest.TestCase):
 def run_signer(self,request):
  import sys
  output=io.StringIO()
  with contextlib.redirect_stdout(output),unittest.mock.patch.object(sys,'stdin',io.StringIO(json.dumps(request))):
   exec(compile(SIGNER,'<private-signer>','exec'),{})
  return output.getvalue().strip()
 def test_config_is_explicit_and_stays_on_signer(self):
  with tempfile.TemporaryDirectory() as temporary:
   config=Path(temporary)/'device_config.h';config.write_text('#define DISPLAY_TOKEN "unit-test-only-token"\n')
   nonce='0'*32
   actual=self.run_signer({'nonce':nonce,'device':'epaper-01','config_path':str(config)})
   expected=hmac.new(b'unit-test-only-token',('PCBLE1\nepaper-01\n'+nonce).encode(),hashlib.sha256).hexdigest()
   self.assertEqual(actual,expected)
 def test_missing_config_refused(self):
  with self.assertRaisesRegex(AssertionError,'config path is required'):
   self.run_signer({'nonce':'0'*32,'device':'epaper-01'})

if __name__=='__main__':
 unittest.main()
