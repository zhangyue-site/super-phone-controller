import io,json,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from display_service import app_control,app_screen
from display_service.app_ota import Authority
from display_service.paired_control import Pairings

class Handler:
 command='POST'
 path='/app-control/screen-renew'
 def __init__(self,bearer,ticket,**extra):
  raw=json.dumps(dict(ticket=ticket,**extra)).encode();self.rfile=io.BytesIO(raw)
  self.headers={'Authorization':'Bearer '+bearer,'Content-Length':str(len(raw))}
 def reply(self,status,body):self.status=status;self.result=json.loads(body)

class ScreenRenewTests(unittest.TestCase):
 def setUp(self):
  self.now=100.;self.control=Authority(clock=lambda:self.now);self.screen=Authority(clock=lambda:self.now)
  self.parent='p'*43;self.ticket='s'*43
  self.control.tickets[self.parent]=(400.,'board-a','proof')
  self.screen.tickets[self.ticket]=(150.,'board-a','usb-screen')
  self.job=SimpleNamespace(screen_session=self.ticket,video_sequence=19,cancelled=False)
  self.mailbox=SimpleNamespace(jobs={'board-a':self.job},cancel=Mock())
  self.patches=[patch.object(app_control,'AUTHORITY',self.control),patch.object(app_screen,'AUTHORITY',self.screen),
   patch.object(app_screen,'SEQUENCES',{self.ticket:27}),patch.object(app_screen,'CONVERSATION',SimpleNamespace(mailbox=self.mailbox)),
   patch.object(app_control,'PAIRINGS',Pairings(lambda ticket:app_control.owner(ticket)[3])),patch.dict('os.environ',{'EPAPER_REMOTE_CONTROL':'1'})]
  for p in self.patches:p.start();self.addCleanup(p.stop)
 def request(self,parent=None,ticket=None,**extra):
  h=Handler(parent or self.parent,ticket or self.ticket,**extra)
  self.assertTrue(app_control.handle(h,None));return h.status,h.result
 def test_owner_renews_same_ticket_without_touching_frame_or_mailbox(self):
  self.assertEqual(self.request(),(200,{'scope':'screen-frames','expiresIn':300}))
  self.assertEqual(self.screen.tickets,{self.ticket:(400.,'board-a','usb-screen')})
  self.assertEqual(app_screen.subject(self.ticket),'board-a')
  self.assertEqual(app_screen.SEQUENCES,{self.ticket:27})
  self.assertEqual((self.job.screen_session,self.job.video_sequence,self.job.cancelled),(self.ticket,19,False))
  self.mailbox.cancel.assert_not_called()
  self.now=350.;self.control.tickets[self.parent]=(650.,'board-a','proof')
  self.assertEqual(self.request()[0],200)
  self.assertEqual(self.screen.tickets[self.ticket][0],650.)
  self.assertEqual(app_screen.SEQUENCES[self.ticket],27)
 def test_cross_device_owner_rejected_without_extension(self):
  self.control.tickets[self.parent]=(400.,'board-b','proof')
  self.assertEqual(self.request()[0],403);self.assertEqual(self.screen.tickets[self.ticket][0],150.)
 def test_paired_controller_cannot_renew_screen(self):
  issued=app_control.PAIRINGS.issue(self.parent)
  paired=app_control.PAIRINGS.redeem(issued['code'])['ticket']
  self.assertEqual(self.request(parent=paired)[0],403)
  self.assertEqual(self.screen.tickets[self.ticket][0],150.)
 def test_expired_screen_cannot_be_resurrected(self):
  self.now=150.
  self.assertEqual(self.request()[0],403);self.assertNotIn(self.ticket,self.screen.tickets)
 def test_revoked_screen_cannot_be_recreated(self):
  self.screen.tickets.pop(self.ticket)
  self.assertEqual(self.request()[0],403);self.assertNotIn(self.ticket,self.screen.tickets)
 def test_expired_or_revoked_target_owner_cannot_renew(self):
  self.control.tickets[self.parent]=(100.,'board-a','proof')
  self.assertEqual(self.request()[0],403)
  self.control.tickets.pop(self.parent,None)
  self.assertEqual(self.request()[0],403);self.assertEqual(self.screen.tickets[self.ticket][0],150.)
 def test_screen_ticket_cannot_act_as_target_owner(self):
  self.assertEqual(self.request(parent=self.ticket)[0],403)
 def test_extra_fields_and_malformed_screen_ticket_are_rejected(self):
  self.assertEqual(self.request(device='board-a')[0],409)
  self.assertEqual(self.request(ticket='bad')[0],403)
 def test_authority_locks_never_nested(self):
  lock=self.screen.lock;control=self.control.lock;test=self
  class Probe:
   def __enter__(self):
    test.assertFalse(control.locked());return lock.__enter__()
   def __exit__(self,*args):return lock.__exit__(*args)
  self.screen.lock=Probe()
  self.assertEqual(self.request()[0],200)

if __name__=='__main__':unittest.main()
