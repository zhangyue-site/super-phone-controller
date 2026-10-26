import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from display_service.general_nav import GeneralNavigator
from display_service.wechat_nav import ActionFrameChanged
from display_service.dialogue import Mailbox
from display_service.skill_engine import SkillStore,signature
from test_wechat_nav import frame

class FrameReplanTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.m=Mailbox();self.nav=GeneralNavigator(self.m,SkillStore(Path(self.tmp.name)),frame_timeout=.1)
  self.j=self.m.create('synthetic','a'*16,1);self.j.pointer_protocol='absolute-v1';self.j.video_barrier='b'*32
  self.raw=frame(0);self.calls=[]
  self.final=dict(confidence=.99,complete=True,safe=True,verified=True,task='打开设置',application='设置',bounds=[0,50,1000,900],evidence='系统设置页面')
 def run_case(self,trusted=True,repeated=False,other_error=False):
  click=dict(confidence=.97,safe=True,complete=False,screen='launcher',action='click',target_label='设置',bounds=[100,200,200,300],_trusted_launcher_settings=trusted)
  observations=iter([click,click,dict(self.final)])
  self.nav.vision=lambda raw,task,verify:dict(self.final) if verify else next(observations)
  def action(j,command,expected):
   self.calls.append(command['op'])
   if len(self.calls)>1 and (len(self.calls)==2 or repeated):
    j.video_sequence=20
    if other_error:raise ValueError('板端没有确认动作完成')
    raise ActionFrameChanged('frame changed before dispatch')
   return {'op':command['op'],'ok':True,'id':'f'*32}
  with patch.object(self.nav,'_frame',return_value=(self.raw,1,signature(self.raw))) as frames,patch.object(self.nav,'_action',side_effect=action):
   result=self.nav.run(self.j,'打开设置')
  return result,frames
 def test_certified_frame_rejection_reads_newer_frame_and_relocates_once(self):
  result,frames=self.run_case();self.assertIn('已通过',result);self.assertTrue(self.j.navigation_verified)
  self.assertEqual(self.calls,['hid_home','hid_pointer','hid_pointer'])
  self.assertTrue(any(call.kwargs.get('after')==20 for call in frames.call_args_list))
 def test_repeated_rejection_stops_after_one_replan(self):
  with self.assertRaises(ActionFrameChanged):self.run_case(repeated=True)
  self.assertEqual(len(self.calls),3);self.assertFalse(self.j.navigation_verified)
 def test_untrusted_frame_never_replans(self):
  with self.assertRaises(ActionFrameChanged):self.run_case(trusted=False)
  self.assertEqual(len(self.calls),2)
 def test_post_dispatch_or_generic_error_never_replans(self):
  with self.assertRaises(ValueError):self.run_case(other_error=True)
  self.assertEqual(len(self.calls),2)
 def test_typed_rejection_happens_before_mailbox_execution(self):
  with patch.object(self.nav,'_frame',return_value=(self.raw,1,signature(self.raw))),patch.object(self.nav,'_matches_action_frame',return_value=False),patch.object(self.m,'execute') as execute:
   with self.assertRaises(ActionFrameChanged):self.nav._action(self.j,{'op':'hid_pointer'},signature(self.raw))
   execute.assert_not_called()
