import unittest
from unittest.mock import patch
import test_remote_http
from test_wechat_nav import frame
class CapturePlatformHttpTests(unittest.TestCase):
 def test_ios_metadata_is_bound_to_same_live_turn_and_cannot_switch(self):
  c=test_remote_http.RemoteHttpTests('test_bridge_auth_unknown_peer_cross_confirmation_and_stop');c.setUp()
  try:
   j=c.mailbox.create('epaper-01','a'*16,1)
   headers={'Content-Type':'image/jpeg','X-Screen-Sequence':'1','X-Screen-Barrier':j.video_barrier,'X-Screen-Platform':'ios'}
   published=[];original=c.mailbox.ingest_video
   def observed(*args,**kwargs):
    value=original(*args,**kwargs);published.append((bool(j.video),getattr(j,'video_platform',None)));return value
   with patch.object(c.mailbox,'ingest_video',side_effect=observed):
    code,result=c.request('/app-screen/frame',frame(0),'screen',headers)
   self.assertEqual(published,[(True,'ios')])
   self.assertEqual(code,200);self.assertEqual(j.video_platform,'ios')
   before=j.video_sequence
   headers.update({'X-Screen-Sequence':'2','X-Screen-Platform':'android'})
   self.assertEqual(c.request('/app-screen/frame',frame(0),'screen',headers)[0],403)
   self.assertEqual(j.video_sequence,before);self.assertEqual(j.video_platform,'ios')
   headers['X-Screen-Platform']='ios; shell'
   self.assertEqual(c.request('/app-screen/frame',frame(0),'screen',headers)[0],403)
  finally:c.tearDown()
