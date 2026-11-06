"""Authenticated, short-lived screen-state observations; no phone or actuator."""
import contextlib,io,json,unittest
from email.message import Message
from types import SimpleNamespace
from unittest.mock import Mock,patch
from display_service import app_screen
from display_service.app_ota import Authority
from display_service.dialogue import Mailbox
from display_service.wechat_nav import WechatNavigator

class Handler:
 command='POST';path='/app-screen/status'
 def reply(self,status,body,kind=None):self.status=status;self.value=json.loads(body)

class ScreenStateDiagnosticsTests(unittest.TestCase):
 def setUp(self):
  self.now=100.;self.ticket='t'*43;self.device='test-board'
  self.auth=Authority(clock=lambda:self.now)
  self.auth.tickets[self.ticket]=(400.,self.device,'screen')
  self.m=Mailbox(clock=lambda:self.now);self.j=self.m.create(self.device,'a'*16,1);self.j.screen_session=self.ticket
  self.m.execute=Mock(side_effect=AssertionError('diagnosis cannot dispatch'))
  self.nav=WechatNavigator(self.m,None,frame_timeout=.01)
  self.patches=[patch.object(app_screen,'AUTHORITY',self.auth),patch.object(app_screen,'CONVERSATION',SimpleNamespace(mailbox=self.m)),patch.object(app_screen,'STORE',SimpleNamespace(catalog=lambda device:[]))]
  if hasattr(app_screen,'SCREEN_STATES'):
   self.patches.append(patch.object(app_screen,'SCREEN_STATES',type(app_screen.SCREEN_STATES)()))
  for p in self.patches:p.start()
 def tearDown(self):
  self.m.execute.assert_not_called()
  for p in reversed(self.patches):p.stop()
 def status(self,interactive=None,locked=None,ticket=None,body=b'',duplicate=None):
  h=Handler();h.rfile=io.BytesIO(body);headers=Message()
  headers['Authorization']='Bearer '+(ticket or self.ticket);headers['Content-Length']=str(len(body))
  if interactive is not None:headers['X-Screen-Interactive']=interactive
  if locked is not None:headers['X-Screen-Keyguard-Locked']=locked
  if duplicate:headers[duplicate]='1'
  h.headers=headers;app_screen.handle(h,None);return h
 def diagnosis(self):
  out=io.StringIO()
  with contextlib.redirect_stdout(out):reason=self.nav._frame_timeout_reason(self.j,7)
  line=next(x for x in out.getvalue().splitlines() if x.startswith('FRAME_WAIT_TIMEOUT '))
  return reason,json.loads(line.split(' ',1)[1])
 def test_fresh_locked_state_reports_system_unlock_without_replay(self):
  self.assertEqual(self.status('1','1').status,200)
  message,log=self.diagnosis()
  self.assertEqual(log.get('reason'),'screen_locked');self.assertIn('系统解锁',message)
  self.assertIn('共享授权仍有效',message);self.assertNotIn('共享仍有效，',message)
  self.assertNotIn(self.ticket,json.dumps(log));self.assertTrue(log['share_authorized'])
  self.assertTrue(log['device_share_authorized'])
 def test_fresh_screen_off_is_distinct_from_locked(self):
  self.status('0','0');message,log=self.diagnosis()
  self.assertEqual(log.get('reason'),'screen_off');self.assertIn('息屏',message)
 def test_awake_state_does_not_invent_a_locked_phone(self):
  self.status('1','0');message,log=self.diagnosis()
  self.assertEqual(log.get('reason'),'awake');self.assertIn('原因尚未确认',message)
  self.assertIn('页面静止',message);self.assertNotIn('开启“静态页面',message)
 def test_legacy_status_remains_compatible_and_unknown(self):
  self.assertEqual(self.status().status,200)
  message,log=self.diagnosis();self.assertEqual(log.get('reason'),'unknown')
  self.assertIn('共享授权仍有效',message);self.assertIn('原因尚未确认',message)
 def test_invalid_incomplete_or_duplicate_headers_discard_previous_state(self):
  cases=[('1',None,None),(None,'0',None),('true','0',None),('0','2',None),(' 1','0',None),('1','0','X-Screen-Interactive'),('1','0','X-Screen-Keyguard-Locked')]
  for interactive,locked,duplicate in cases:
   with self.subTest(interactive=interactive,locked=locked,duplicate=duplicate):
    self.status('1','1');self.assertEqual(self.status(interactive,locked,duplicate=duplicate).status,200)
    self.assertEqual(self.diagnosis()[1].get('reason'),'unknown')
  self.status('1','1');self.status();self.assertEqual(self.diagnosis()[1].get('reason'),'unknown')
 def test_five_second_max_age_uses_server_clock(self):
  self.status('1','1');self.now+=5
  self.assertEqual(self.diagnosis()[1].get('reason'),'screen_locked')
  self.now+=.001;message,log=self.diagnosis()
  self.assertEqual(log.get('reason'),'unknown');self.assertIn('原因尚未确认',message)
 def test_capture_replacement_never_borrows_previous_ticket_state(self):
  self.status('1','1');other='u'*43
  self.auth.tickets.pop(self.ticket);self.auth.tickets[other]=(400.,self.device,'screen')
  self.j.screen_session=other
  self.assertEqual(self.diagnosis()[1].get('reason'),'unknown')
 def test_another_capture_and_device_cannot_supply_state(self):
  other='u'*43;self.auth.tickets[other]=(400.,self.device,'screen');self.status('1','1',ticket=other)
  self.assertEqual(self.diagnosis()[1].get('reason'),'unknown')
  self.auth.tickets[other]=(400.,'other-board','screen');self.status('0','1',ticket=other)
  self.assertEqual(self.diagnosis()[1].get('reason'),'unknown')
 def test_revoked_or_expired_grant_cannot_supply_state(self):
  for invalid in ('revoked','expired'):
   with self.subTest(invalid=invalid):
    self.auth.tickets[self.ticket]=(400.,self.device,'screen');self.status('1','1')
    if invalid=='revoked':self.auth.tickets.pop(self.ticket)
    else:self.auth.tickets[self.ticket]=(self.now,self.device,'screen')
    _,log=self.diagnosis();self.assertFalse(log['share_authorized']);self.assertEqual(log.get('reason'),'unknown')
 def test_mismatched_device_never_borrows_ticket_observation(self):
  self.status('1','1');self.j.device='other-board';_,log=self.diagnosis()
  self.assertFalse(log['share_authorized']);self.assertEqual(log.get('reason'),'unknown')
 def test_unauthenticated_or_nonempty_status_cannot_update_observation(self):
  self.assertEqual(self.status('1','1',ticket='x'*43).status,403)
  self.assertEqual(self.status('1','1',body=b'x').status,403)
  self.assertEqual(self.diagnosis()[1].get('reason'),'unknown')
 def test_validated_status_is_bounded_without_evicting_current_authority(self):
  for n in range(257):
   ticket=f'{n:043d}';self.auth.tickets[ticket]=(400.,self.device,'screen');self.status('1','1',ticket=ticket)
  self.j.screen_session=f'{0:043d}';self.assertEqual(self.diagnosis()[1].get('reason'),'unknown')
  self.j.screen_session=f'{256:043d}';self.assertEqual(self.diagnosis()[1].get('reason'),'screen_locked')
 def test_first_frame_missing_uses_diagnostic_link_without_granting_frame_permission(self):
  self.j.screen_session='';before=(self.j.video,self.j.video_sequence,self.j.video_barrier)
  reply=self.status('0','1');message,log=self.diagnosis()
  self.assertFalse(reply.value['pointerReady'])
  self.assertEqual(log.get('reason'),'screen_locked');self.assertTrue(log['share_authorized'])
  self.assertIn('系统解锁',message);self.assertEqual(self.j.screen_session,'')
  self.assertEqual((self.j.video,self.j.video_sequence,self.j.video_barrier),before)
  with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(ValueError,'系统解锁'):
   self.nav._frame(self.j,after=0)
  self.m.execute.assert_not_called()
 def test_first_frame_missing_legacy_or_stale_state_is_unknown(self):
  self.j.screen_session='';self.status()
  self.assertEqual(self.diagnosis()[1].get('reason'),'unknown')
  self.status('0','1');self.now+=5.001
  self.assertEqual(self.diagnosis()[1].get('reason'),'unknown')
 def test_first_frame_diagnostics_do_not_attach_to_another_new_job(self):
  self.j.screen_session='';self.status('0','1')
  self.m.cancel(self.device);self.j=self.m.create(self.device,'b'*16,1)
  self.assertEqual(self.j.screen_session,'')
  _,log=self.diagnosis();self.assertEqual(log.get('reason'),'unknown');self.assertFalse(log['share_authorized'])
  self.status('0','1');self.assertEqual(self.diagnosis()[1].get('reason'),'screen_locked')
 def test_terminal_or_replaced_job_cannot_read_diagnostic_link(self):
  for terminal in ('done','cancelled','replaced'):
   with self.subTest(terminal=terminal):
    self.m.cancel(self.device)
    self.j=self.m.create(self.device,('c' if terminal=='done' else 'd' if terminal=='cancelled' else 'e')*16,1)
    self.j.screen_session='';self.status('0','1');old=self.j
    if terminal=='replaced':self.m.cancel(self.device);self.m.create(self.device,'f'*16,1)
    else:setattr(self.j,terminal,True)
    _,log=self.diagnosis();self.assertEqual(log.get('reason'),'unknown');self.assertFalse(log['share_authorized'])
    self.j=old
 def test_two_valid_captures_without_real_frame_are_ambiguous(self):
  self.j.screen_session='';other='u'*43;self.auth.tickets[other]=(400.,self.device,'screen')
  self.status('0','1');self.status('1','0',ticket=other)
  self.assertEqual(self.diagnosis()[1].get('reason'),'unknown')
 def test_new_ambiguity_does_not_keep_first_old_diagnostic_link(self):
  self.j.screen_session='';self.status('0','1')
  self.assertEqual(self.diagnosis()[1].get('reason'),'screen_locked')
  other='u'*43;self.auth.tickets[other]=(400.,self.device,'screen');self.status('1','0',ticket=other)
  self.assertEqual(self.diagnosis()[1].get('reason'),'unknown')
 def test_real_frame_binding_wins_and_never_falls_back_to_diagnostic_capture(self):
  self.j.screen_session='';self.status('0','1')
  other='u'*43;self.auth.tickets[other]=(400.,self.device,'screen');self.j.screen_session=other
  self.status('1','0',ticket=other);self.assertEqual(self.diagnosis()[1].get('reason'),'awake')
  self.status('0','1');self.assertEqual(self.diagnosis()[1].get('reason'),'awake')
  self.auth.tickets.pop(other)
  _,log=self.diagnosis();self.assertEqual(log.get('reason'),'unknown');self.assertFalse(log['share_authorized'])
 def test_replaced_diagnostic_capture_requires_its_own_new_status(self):
  self.j.screen_session='';self.status('0','1');self.auth.tickets.pop(self.ticket)
  other='u'*43;self.auth.tickets[other]=(400.,self.device,'screen')
  self.assertEqual(self.diagnosis()[1].get('reason'),'unknown')
  self.status('1','0',ticket=other);self.assertEqual(self.diagnosis()[1].get('reason'),'awake')
 def test_other_device_status_cannot_bind_first_frame_diagnostics(self):
  self.j.screen_session='';other='u'*43;self.auth.tickets[other]=(400.,'other-board','screen')
  self.status('0','1',ticket=other)
  _,log=self.diagnosis();self.assertEqual(log.get('reason'),'unknown');self.assertFalse(log['share_authorized'])
 def test_unattributed_valid_capture_does_not_claim_sharing_was_not_started(self):
  for situation in ('ambiguous','new_job_without_status'):
   with self.subTest(situation=situation):
    self.j.screen_session=''
    if situation=='ambiguous':self.auth.tickets['u'*43]=(400.,self.device,'screen')
    else:self.auth.tickets.pop('u'*43,None)
    message,log=self.diagnosis()
    self.assertEqual(log.get('reason'),'unknown');self.assertFalse(log['share_authorized'])
    self.assertIn('无法确认本次任务的共享状态',message);self.assertNotIn('请在App中共享',message)
    self.assertTrue(log['device_share_authorized'])
 def test_no_valid_device_grant_keeps_existing_share_prompt(self):
  self.j.screen_session='';self.auth.tickets.clear()
  message,log=self.diagnosis();self.assertEqual(log.get('reason'),'unknown')
  self.assertIn('请在App中共享整个屏幕',message)
  self.assertFalse(log['share_authorized']);self.assertFalse(log['device_share_authorized'])
 def test_status_protocol_over_real_http_accepts_optional_headers_and_legacy(self):
  self.j.screen_session=''
  import http.client,threading
  from http.server import ThreadingHTTPServer
  from display_service import app
  server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
  thread=threading.Thread(target=server.serve_forever);thread.start()
  def post(headers):
   conn=http.client.HTTPConnection(*server.server_address,timeout=3)
   try:
    conn.request('POST','/app-screen/status',body=b'',headers=dict({'Authorization':'Bearer '+self.ticket},**headers))
    response=conn.getresponse();body=response.read();return response.status,json.loads(body)
   finally:conn.close()
  try:
   status,value=post({'X-Screen-Interactive':'1','X-Screen-Keyguard-Locked':'1'})
   self.assertEqual(status,200);self.assertIn('barrier',value)
   self.assertFalse(value['pointerReady']);self.assertEqual(self.j.screen_session,'')
   self.assertEqual(self.diagnosis()[1].get('reason'),'screen_locked')
   self.assertEqual(post({'X-Screen-Interactive':'oops','X-Screen-Keyguard-Locked':'0'})[0],200)
   self.assertEqual(self.diagnosis()[1].get('reason'),'unknown')
   self.assertEqual(post({})[0],200)
  finally:server.shutdown();server.server_close();thread.join()
 def test_actual_frame_timeout_is_diagnostic_only(self):
  self.status('1','1')
  with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(ValueError,'系统解锁'):
   self.nav._frame(self.j,after=7)
  self.m.execute.assert_not_called()

if __name__=='__main__':unittest.main()
