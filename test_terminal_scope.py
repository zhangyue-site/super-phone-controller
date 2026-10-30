import json,time,threading,unittest,tempfile,hashlib,hmac,io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from display_service import app_screen
from display_service.app_ota import Authority
from display_service.dialogue import Mailbox
from display_service.conversation import Conversation
class Handler:
 command='POST';path='/app-screen/status'
 def __init__(self,ticket):self.headers={'Authorization':'Bearer '+ticket,'Content-Length':'0'}
 def reply(self,status,body,kind=None):self.status=status;self.result=json.loads(body)
class TerminalScopeTests(unittest.TestCase):
 def setUp(self):
  self.now=0.;self.ticket='t'*43;self.auth=Authority(clock=lambda:self.now);self.auth.tickets[self.ticket]=(300.,'board','screen')
  self.m=Mailbox(clock=lambda:self.now);self.j=self.m.create('board','a'*16,1)
  self.j.done=True;self.j.state='done';self.j.navigation_verified=True;self.j.reply='已独立核验';self.j.screen_session=self.ticket;self.j.audio=b'audio';self.j.video=b'video';self.j.video_sequence=12;self.j.pointer_protocol='absolute-v1'
  self.c=Conversation.__new__(Conversation);self.c.mailbox=self.m;self.c.status=lambda *a:None;self.c.history_lock=threading.RLock();self.c.histories={};self.c.history_times={}
  self.patches=[patch.object(app_screen,'AUTHORITY',self.auth),patch.object(app_screen,'CONVERSATION',SimpleNamespace(mailbox=self.m)),patch.object(app_screen.STORE,'catalog',return_value=[])]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
 def status(self,ticket=None):
  h=Handler(ticket or self.ticket);app_screen.handle(h,None);return h.status,h.result
 def test_done_61_seconds_releases_media_but_keeps_scoped_verified_result(self):
  self.now=61.;self.c.expire();self.assertFalse(self.j.cancelled);self.assertEqual((self.j.audio,self.j.video),(b'',b''))
  code,result=self.status();self.assertEqual(code,200);self.assertEqual(result['state'],'done');self.assertIs(result['verified'],True);self.assertEqual(result['reply'],'已独立核验')
 def test_old_live_action_is_rejected_without_mutating_terminal_or_touch(self):
  self.now=61.;before=self.j.touched
  for f in (lambda:self.m._live(self.j),lambda:self.m.offer(self.j,{'op':'hid_home'}),lambda:self.m.poll('board','a'*16,1)):
   with self.assertRaises(ValueError):f()
  self.assertEqual(self.j.touched,before);self.assertFalse(self.j.cancelled);self.assertIsNone(self.j.command)
  self.assertIs(self.status()[1]['verified'],True)
 def test_fresh_completed_job_cannot_accept_any_new_action(self):
  with self.assertRaises(ValueError):self.m.offer(self.j,{'op':'hid_home'})
  self.assertIsNone(self.j.command)
 def test_other_scope_cannot_read_reply_or_barrier(self):
  other='u'*43;self.auth.tickets[other]=(300.,'board','screen')
  code,result=self.status(other);self.assertEqual(code,200);self.assertEqual(result['state'],'idle');self.assertEqual(result['reply'],'');self.assertIs(result['verified'],False);self.assertEqual(result['frame'],0);self.assertEqual(result['barrier'],'')
 def test_stop_and_ticket_revocation_hide_result(self):
  self.m.cancel('board');self.assertEqual(self.status()[1]['state'],'idle');self.assertIs(self.status()[1]['verified'],False);self.assertEqual(self.status()[1]['barrier'],'')
  self.auth.tickets.pop(self.ticket);self.assertEqual(self.status()[0],403)
 def test_new_task_replaces_terminal_without_old_success(self):
  new=self.m.create('board','a'*16,2);new.reply='新任务';new.screen_session=self.ticket
  code,result=self.status();self.assertEqual(code,200);self.assertEqual(result['reply'],'新任务');self.assertIs(result['verified'],False);self.assertNotEqual(result['state'],'done')
 def test_failed_terminal_never_promoted_and_active_expiry_still_cancels(self):
  self.j.state='error';self.now=61.;self.c.expire();self.assertEqual(self.status()[1]['state'],'error');self.assertIs(self.status()[1]['verified'],False)
  self.j.done=False;self.c.expire();self.assertTrue(self.j.cancelled);self.assertEqual(self.status()[1]['state'],'idle')
 def test_revocation_between_subject_lookup_and_snapshot_is_rechecked(self):
  original=app_screen.subject
  def revoked(ticket):
   device=original(ticket);self.auth.tickets.pop(ticket);return device
  with patch.object(app_screen,'subject',side_effect=revoked):self.assertEqual(self.status()[0],403)
 def test_status_never_renews_execution_lifetime_and_max_age_actions_fail(self):
  self.now=181.;created=self.j.created;touched=self.j.touched
  with self.assertRaises(ValueError):self.m._live(self.j)
  self.assertEqual(self.status()[1]['state'],'done');self.assertIs(self.status()[1]['verified'],True)
  self.assertEqual((self.j.created,self.j.touched,self.j.max_age),(created,touched,180));self.assertFalse(self.j.cancelled)
 def test_truthy_verification_text_is_not_boolean_proof(self):
  self.j.navigation_verified='false';self.assertIs(self.status()[1]['verified'],False)
 def test_real_new_authorization_supersedes_capture_and_hides_old_result(self):
  keys={'board':'synthetic-only'};challenge=self.auth.challenge('board',keys)['challenge']
  proof=hmac.new(b'synthetic-only',b'PCFLASH1\nboard\n'+bytes.fromhex(challenge),hashlib.sha256).hexdigest()
  obj=dict(device='board',challenge=challenge,proof=proof);raw=json.dumps(obj).encode();h=Handler(self.ticket);h.path='/app-screen/authorize';h.headers['Content-Length']=str(len(raw));h.rfile=io.BytesIO(raw)
  with tempfile.TemporaryDirectory() as tmp:
   config=Path(tmp)/'devices.json';config.write_text(json.dumps(keys))
   with patch('display_service.firmware.release',return_value=({'sha256':'f'*64,'version':'test','size':100},b'')):app_screen.handle(h,config)
  self.assertEqual(h.status,200);self.assertEqual(self.status()[0],403);self.assertEqual(self.status(h.result['ticket'])[1]['state'],'idle');self.assertTrue(self.j.cancelled)
if __name__=='__main__':unittest.main()
