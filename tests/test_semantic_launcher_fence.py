import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from display_service.general_nav import GeneralNavigator
from display_service.dialogue import Mailbox
from display_service.skill_engine import SkillStore

class SemanticLauncherFenceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.nav=GeneralNavigator(Mailbox(),SkillStore(Path(self.tmp.name)));self.expected={'w':640,'h':1280,'_blank_launcher':True};self.current={'w':640,'h':1280}
  self.gate={'screen':'launcher','bounds':[450,630,550,670],'end':[500,250],'_trusted_launcher_blank':True}
 def matches(self,gate,clear=True):
  with patch('display_service.wechat_nav.WechatNavigator._matches_action_frame',return_value=False),patch('display_service.launcher_guard.structure_metrics',return_value={'same':False}),patch('display_service.jev_vision.clear_swipe_region',return_value=clear),patch('display_service.jev_vision.observe_launcher',return_value=gate):return self.nav._matches_action_frame(self.expected,self.current,b'new-current-frame')
 def test_icon_layout_change_can_use_new_independently_verified_launcher(self):self.assertTrue(self.matches(self.gate))
 def test_other_page_is_not_allowed_even_when_blank(self):self.assertFalse(self.matches(None));self.assertFalse(self.matches(dict(self.gate,screen='calculator')))
 def test_occupied_swipe_patch_is_not_allowed(self):self.assertFalse(self.matches(self.gate,clear=False))
 def test_geometry_change_is_not_allowed(self):self.current['w']=1280;self.assertFalse(self.matches(self.gate))
 def test_icon_click_never_gets_semantic_swipe_exception(self):self.expected={'w':640,'h':1280,'_launcher_settings':True};self.assertFalse(self.matches(self.gate))
