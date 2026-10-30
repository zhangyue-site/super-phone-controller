import tempfile,unittest,types,os,json,stat
from pathlib import Path
from unittest.mock import patch
from display_service.general_nav import GeneralNavigator
from display_service.dialogue import Mailbox
from display_service.skill_engine import SkillStore,signature,region
from display_service.wechat_nav import ActionFrameChanged
from test_action_frame_budget import frame
class EvidenceTests(unittest.TestCase):
 def test_rejected_frame_metadata_and_private_cap_do_not_authorize_action(self):
  with tempfile.TemporaryDirectory() as tmp:
   m=Mailbox();j=m.create('synthetic','a'*16,1);j.remote_task_id='b'*32
   nav=GeneralNavigator(m,SkillStore(Path(tmp)/'skills'));raw=frame(0);expected=signature(raw);expected.update(target=region(raw,[100,100,300,200]),_observation_frame=7)
   with patch.object(nav,'_frame',return_value=(frame(1),8,signature(frame(1)))),patch.object(nav,'_matches_action_frame',return_value=False),patch.object(m,'execute') as execute,patch.dict(os.environ,{'EPAPER_NAV_EVIDENCE_DIR':tmp}):
    with self.assertRaises(ActionFrameChanged):nav._action(j,dict(op='hid_text'),expected)
    execute.assert_not_called()
    files=list((Path(tmp)/j.remote_task_id).glob('*.jpg'));self.assertEqual(len(files),1);self.assertEqual(files[0].stat().st_mode&0o777,0o600)
    details=json.loads(files[0].with_suffix('.json').read_text());self.assertEqual((details['observed_frame'],details['current_frame']),(7,8));self.assertFalse(details['scene_same']);self.assertFalse(details['target_same'])
    for seq in range(9,16):nav._record_frame_rejection(j,dict(op='hid_text'),expected,frame(1),signature(frame(1)),seq)
    self.assertEqual(len(list((Path(tmp)/j.remote_task_id).glob('*.jpg'))),4)
 def test_without_explicit_evidence_directory_no_images_are_created(self):
  with tempfile.TemporaryDirectory() as tmp:
   m=Mailbox();j=m.create('synthetic','a'*16,1);nav=GeneralNavigator(m,SkillStore(Path(tmp)/'skills'))
   raw=frame(0);expected=signature(raw)
   with patch.dict(os.environ,{},clear=True),patch.object(nav,'_log') as log:nav._record_frame_rejection(j,{'op':'hid_text'},expected,raw,expected,2)
   self.assertEqual(list(Path(tmp).glob('*.jpg')),[]);self.assertEqual(log.call_args.args[1],'frame_guard_rejected')
if __name__=='__main__':unittest.main()
