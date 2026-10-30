import io,json,unittest
from types import SimpleNamespace
from unittest.mock import patch
from display_service import app_screen
from display_service.app_ota import Authority
from display_service.dialogue import Mailbox
from PIL import Image
def frame(stage):
 out=io.BytesIO();Image.new('RGB',(240,480),'white').save(out,format='JPEG');return out.getvalue()
class Handler:
 command='POST';path='/app-screen/frame'
 def reply(self,status,body,kind=None):self.status=status;self.value=json.loads(body)
class Tests(unittest.TestCase):
 def setUp(self):
  self.m=Mailbox();self.j=self.m.create('board','a'*16,1);self.j.fenced=True;self.ticket='t'*43;self.j.screen_session=self.ticket
  self.auth=Authority();self.auth.tickets[self.ticket]=(self.auth.clock()+300,'board','screen')
  self.patches=[patch.object(app_screen,'AUTHORITY',self.auth),patch.object(app_screen,'CONVERSATION',SimpleNamespace(mailbox=self.m)),patch.object(app_screen,'SEQUENCES',{})]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
 def request(self,raw=None,ticket=None,sequence=1):
  raw=frame(0) if raw is None else raw;h=Handler();h.rfile=io.BytesIO(raw);h.headers={'Authorization':'Bearer '+(ticket or self.ticket),'Content-Type':'image/jpeg','Content-Length':str(len(raw)),'X-Screen-Sequence':str(sequence),'X-Screen-Barrier':self.j.video_barrier};app_screen.handle(h,None);return h
 def test_home_ack_rotating_barrier_drops_inflight_frame_without_auth_failure(self):
  self.m.offer(self.j,{'op':'hid_home'});cmd=self.m.poll('board','a'*16,1);before=self.j.video_barrier;original=self.m.ingest_video
  def raced(*args,**kw):self.m.ack('board','a'*16,1,cmd['id'],True,'HID_HOME_REPORT_SENT');return original(*args,**kw)
  with patch.object(self.m,'ingest_video',side_effect=raced):h=self.request()
  self.assertEqual(h.status,202);self.assertIs(h.value['accepted'],False);self.assertNotEqual(before,self.j.video_barrier);self.assertEqual(h.value['barrier'],self.j.video_barrier);self.assertFalse(self.j.cancelled);self.assertFalse(self.j.video)
 def test_new_job_before_ingest_drops_old_payload_and_does_not_bind_new_scope(self):
  original=self.m.ingest_video;new=[]
  def raced(*a,**k):self.j.done=True;new.append(self.m.create('board','a'*16,2));return original(*a,**k)
  with patch.object(self.m,'ingest_video',side_effect=raced):h=self.request()
  self.assertEqual(h.status,202);self.assertIs(h.value['accepted'],False);self.assertEqual(h.value['barrier'],'0'*32);self.assertFalse(new[0].cancelled);self.assertFalse(new[0].video);self.assertEqual(new[0].screen_session,'')
 def test_new_job_after_ingest_never_accepts_old_payload(self):
  original=self.m.ingest_video;new=[]
  def raced(*a,**k):
   result=original(*a,**k);self.j.done=True;new.append(self.m.create('board','a'*16,2));new[0].screen_session=self.ticket;return result
  with patch.object(self.m,'ingest_video',side_effect=raced):h=self.request()
  self.assertEqual(h.status,202);self.assertIs(h.value['accepted'],False);self.assertEqual(h.value['barrier'],new[0].video_barrier);self.assertFalse(new[0].video)
 def test_revoked_ticket_remains_403_even_when_barrier_rotates(self):
  def raced(*a,**k):self.auth.tickets.pop(self.ticket);self.j.video_barrier='f'*32;raise ValueError('capture barrier required')
  with patch.object(self.m,'ingest_video',side_effect=raced):self.assertEqual(self.request().status,403)
 def test_current_job_with_different_capture_scope_remains_403(self):
  original=self.m.ingest_video
  def raced(*a,**k):self.j.done=True;new=self.m.create('board','a'*16,2);new.screen_session='u'*43;return original(*a,**k)
  with patch.object(self.m,'ingest_video',side_effect=raced):self.assertEqual(self.request().status,403)
 def test_bad_image_and_wrong_sequence_remain_403(self):
  self.assertEqual(self.request(raw=b'not jpeg').status,403);self.assertEqual(self.request(sequence=1).status,403)
 def test_unrelated_value_error_not_hidden_even_if_job_ends(self):
  def raced(*a,**k):self.j.done=True;raise ValueError('invalid image')
  with patch.object(self.m,'ingest_video',side_effect=raced):self.assertEqual(self.request().status,403)
 def test_revocation_after_ingest_is_still_auth_failure(self):
  original=self.m.ingest_video
  def raced(*a,**k):
   result=original(*a,**k);self.auth.tickets.pop(self.ticket);return result
  with patch.object(self.m,'ingest_video',side_effect=raced):self.assertEqual(self.request().status,403)
if __name__=='__main__':unittest.main()
