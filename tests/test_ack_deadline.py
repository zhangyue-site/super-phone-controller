import unittest
from display_service.dialogue import Mailbox
class AckDeadlineTests(unittest.TestCase):
 def test_single_offer_accepts_current_ack_after_forty_seconds(self):
  now=[0.];m=Mailbox(clock=lambda:now[0]);j=m.create('synthetic','a'*16,1)
  class Event:
   def clear(self):pass
   def set(self):pass
   def wait(self,_):
    now[0]+=10
    m.poll(j.device,j.session,j.sequence)
    if now[0]==40:m.ack(j.device,j.session,j.sequence,j.command['id'],True,'HID_HOME_REPORT_SENT')
  j.event=Event()
  self.assertEqual(m.execute(j,{'op':'hid_home'}),'HID_HOME_REPORT_SENT')
  self.assertEqual(now[0],40)
  self.assertIsNone(j.command)
