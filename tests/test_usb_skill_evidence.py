import unittest,tempfile
from types import SimpleNamespace
from display_service.skill_engine import SkillStore,WorkflowSpec
class UsbSkillEvidence(unittest.TestCase):
 def test_real_keyboard_receipt_is_collectable_but_not_assumed(self):
  with tempfile.TemporaryDirectory() as d:
   store=SkillStore(d);spec=WorkflowSpec('general.navigate','通用','画面导航',('task',),'general.verified')
   job=SimpleNamespace(device='d',sequence=1)
   step=dict(receipt=dict(id='a'*32,op='hid_text',ok=True),signature={},target={})
   proof=dict(verified=True,terminal='general.verified',parameters={'task':'搜索北京'})
   store.remember(job,spec,{'task':'搜索北京'},[step],[640,1280],dict(op='hid_home',ok=True),proof)
   step['receipt']['ok']=False
   with self.assertRaises(ValueError):store.remember(job,spec,{'task':'搜索北京'},[step],[640,1280],dict(op='hid_home',ok=True),proof)
if __name__=='__main__':unittest.main()
