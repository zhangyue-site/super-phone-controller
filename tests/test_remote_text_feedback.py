import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from display_service.conversation import Conversation
from display_service.dialogue import Mailbox
from display_service.wechat_nav import SkillStore
class Navigation:
 def run(self,j,text):j.navigation_verified=True;return '已核验设置页'
class BadNavigation:
 def run(self,j,text):raise ValueError('no real frame')
class RemoteTextFeedbackTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.calls=[];self.mailbox=Mailbox()
  self.c=Conversation(self.mailbox,model=lambda _:{'action':'reply','reply':'hello'},tts=lambda text:self.calls.append(text) or b'',status=lambda *a:None,skills=SkillStore(Path(self.temp.name)),general_navigator=Navigation())
 def tearDown(self):self.temp.cleanup()
 def test_verified_remote_navigation_does_not_depend_on_tts(self):
  j=self.mailbox.create('synthetic','a'*16,1);j.remote_task_id='b'*32
  with patch.dict(os.environ,{'EPAPER_WECHAT_NAV':'1'}):self.c.run(j,'打开设置')
  self.assertTrue(j.done and j.navigation_verified);self.assertEqual(j.state,'done');self.assertEqual(self.calls,[]);self.assertFalse(j.speech_error)
 def test_failed_remote_navigation_is_still_failure_without_audio(self):
  self.c.general_navigator=BadNavigation();j=self.mailbox.create('synthetic','a'*16,1);j.remote_task_id='b'*32
  with patch.dict(os.environ,{'EPAPER_WECHAT_NAV':'1'}):self.c.run(j,'打开设置')
  self.assertTrue(j.done);self.assertEqual(j.state,'error');self.assertFalse(j.navigation_verified);self.assertEqual(self.calls,[])
 def test_voice_reply_still_requires_successful_speech(self):
  j=self.mailbox.create('synthetic','a'*16,1);self.c.run(j,'hello')
  self.assertEqual(j.state,'error');self.assertTrue(j.speech_error);self.assertEqual(self.calls,['hello'])
if __name__=='__main__':unittest.main()
