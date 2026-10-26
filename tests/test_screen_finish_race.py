import unittest
from unittest.mock import patch
import test_remote_http
from display_service import app_screen
from test_wechat_nav import frame
class ScreenFinishRaceTests(unittest.TestCase):
 def test_completed_job_during_decode_returns_inactive_not_auth_error(self):self.run_race(False)
 def test_completed_job_before_response_returns_inactive_not_auth_error(self):self.run_race(True)
 def run_race(self,commit):
  c=test_remote_http.RemoteHttpTests('test_bridge_auth_unknown_peer_cross_confirmation_and_stop');c.setUp();app_screen.SEQUENCES.clear()
  try:
   j=c.mailbox.create('epaper-01','a'*16,1);original=c.mailbox.ingest_video
   def finish(*a,**kw):
    if commit:r=original(*a,**kw);j.done=True;return r
    j.done=True;raise ValueError('video superseded')
   with patch.object(c.mailbox,'ingest_video',side_effect=finish):
    code,result=c.request('/app-screen/frame',frame(0),'screen',{'Content-Type':'image/jpeg','X-Screen-Sequence':'1','X-Screen-Barrier':j.video_barrier})
   self.assertEqual(code,202);self.assertFalse(result['accepted']);self.assertEqual(result['barrier'],'0'*32)
  finally:c.tearDown()
if __name__=='__main__':unittest.main()
