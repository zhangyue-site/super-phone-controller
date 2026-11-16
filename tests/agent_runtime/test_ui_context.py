import unittest,tempfile,json,hashlib
from pathlib import Path
from display_service.agent_ui_context import load
class UiContext(unittest.TestCase):
 def test_context_is_bound_to_capture_device_platform_and_expiry(self):
  with tempfile.TemporaryDirectory()as tmp:
   path=Path(tmp)/'context.json';value=dict(v=1,bindings=[dict(device='d',capture_sha256=hashlib.sha256(b's').hexdigest(),platform='android',issued_at=10,expires_at=100,hint='当前已核对手机系统资料，仍需新画面验收',sources=['https://example.com/official'],manufacturer='Example',panel_style='unknown')]);path.write_text(json.dumps(value))
   self.assertEqual(load(path,device='d',session='s',platform='android',now=20)['manufacturer'],'Example')
   for args in [dict(device='other',session='s',platform='android',now=20),dict(device='d',session='new-capture',platform='android',now=20),dict(device='d',session='s',platform='ios',now=20),dict(device='d',session='s',platform='android',now=101)]:self.assertIsNone(load(path,**args))
if __name__=='__main__':unittest.main()
