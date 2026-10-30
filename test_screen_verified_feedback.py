import json,threading,unittest
from types import SimpleNamespace
from unittest.mock import patch
from display_service import app_screen
from display_service.app_ota import Authority
class Handler:
 command='POST';path='/app-screen/status'
 headers={'Authorization':'Bearer '+'x'*43,'Content-Length':'0'}
 def reply(self,status,body):self.status=status;self.result=json.loads(body)
class FeedbackTests(unittest.TestCase):
 def status(self,**changes):
  job=SimpleNamespace(state='done',done=True,cancelled=False,navigation_verified=False,reply='已通过画面核验完成',video_sequence=12,pointer_protocol='absolute-v1',video_barrier='b'*32,screen_session='x'*43)
  for k,v in changes.items():setattr(job,k,v)
  box=SimpleNamespace(lock=threading.RLock(),jobs={'board':job})
  authority=Authority();authority.tickets['x'*43]=(authority.clock()+300,'board','screen')
  with patch.object(app_screen,'AUTHORITY',authority),patch.object(app_screen,'CONVERSATION',SimpleNamespace(mailbox=box)),patch.object(app_screen.STORE,'catalog',return_value=[]):
   h=Handler();self.assertTrue(app_screen.handle(h,None));self.assertEqual(h.status,200);return h.result
 def test_verified_done_has_explicit_true(self):self.assertIs(self.status(navigation_verified=True)['verified'],True)
 def test_success_words_do_not_prove_verification(self):self.assertIs(self.status()['verified'],False)
 def test_cancelled_verified_job_is_false(self):self.assertIs(self.status(navigation_verified=True,cancelled=True)['verified'],False)
 def test_running_job_not_terminal_verified(self):self.assertIs(self.status(navigation_verified=True,done=False,state='running')['verified'],False)
 def test_failed_job_never_verified(self):self.assertIs(self.status(navigation_verified=True,state='error')['verified'],False)
if __name__=='__main__':unittest.main()
