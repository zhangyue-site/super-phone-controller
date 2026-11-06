import unittest
from display_service.usb_window import Windows,WindowExpired
class Tests(unittest.TestCase):
 def setUp(self):self.now=100.;self.w=Windows(clock=lambda:self.now);self.action=('id',1,6)
 def permit(self):return self.w.permit('board','capture','binding',self.action)
 def poll(self):return self.w.request('board','capture',{'operation':'poll'})
 def ready(self,p):return self.w.request('board','capture',dict(operation='ready',**{k:p[k] for k in ('nonce','mode','generation')}))
 def test_client_receive_delay_does_not_spend_its_five_second_confirmation(self):
  self.assertFalse(self.permit());self.now+=6
  self.assertFalse(self.permit());p=self.poll();self.assertEqual(p['expiresInMs'],5000)
  self.now+=4.9;self.ready(p);self.assertTrue(self.permit())
 def test_queue_wait_is_still_bounded_without_any_client(self):
  self.permit();self.now+=30
  with self.assertRaises(WindowExpired):self.permit()
  with self.assertRaises(PermissionError):self.poll()
 def test_poll_retries_cannot_extend_the_confirmation_window(self):
  self.permit();p=self.poll();self.now+=4;p2=self.poll();self.assertLessEqual(p2['expiresInMs'],1000)
  self.assertEqual(p['nonce'],p2['nonce']);self.now+=1
  with self.assertRaises(PermissionError):self.ready(p)
  with self.assertRaises(WindowExpired):self.permit()
 def test_ready_without_observing_prepare_is_rejected(self):
  self.permit();w=self.w.windows['board']
  with self.assertRaises(PermissionError):self.ready(w)
 def test_changed_capture_and_binding_are_still_rejected(self):
  self.permit()
  with self.assertRaises(PermissionError):self.w.request('board','other',{'operation':'poll'})
  with self.assertRaises(WindowExpired):self.w.permit('board','capture','other',self.action)
if __name__=='__main__':unittest.main()
