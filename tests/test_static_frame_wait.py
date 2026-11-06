"""Synthetic phone that, like Android ImageReader, uploads only on screen change.

Not evidence of a real phone, lock screen, or the experimental sampling path.
"""
import io,json,tempfile,threading,time,unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from pathlib import Path
from display_service import app_screen
from display_service.app_ota import Authority
from display_service.dialogue import Mailbox
from display_service.general_nav import GeneralNavigator
from display_service.skill_engine import SkillStore
from test_wechat_nav import frame
OUT={'hid_home':'HID_HOME_REPORT_SENT','hid_pointer':'HID_POINTER_REPORT_SENT'}
class StaticFrameWait(unittest.TestCase):
 def run_task(self,order='receipt-first',shared=True,sampling=False):
  m=Mailbox();j=m.create('synthetic','a'*16,1);j.pointer_protocol='absolute-v1';j.video_source='user-consented-app-screen'
  j.screen_session='static-wait-%s-%s-%s'%(order,shared,sampling)
  if shared:
   with app_screen.AUTHORITY.lock:app_screen.AUTHORITY.tickets[j.screen_session]=(app_screen.AUTHORITY.clock()+300,j.device,'usb-screen')
  self.addCleanup(app_screen.AUTHORITY.tickets.pop,j.screen_session,None)
  stage=[0];ops=[];stop=threading.Event();emitted=[0.0]
  def emit():
   m.ingest_video(j.device,j.session,j.sequence,j.video_sequence+1,frame(min(stage[0],3)),'jpeg',expected_barrier=j.video_barrier,source='user-consented-app-screen')
   emitted[0]=time.monotonic()
  def phone():
   emit()
   while not stop.is_set():
    try:
     c=m.poll(j.device,j.session,j.sequence,'absolute-v1');op=c['op']
     if op not in ('wait','done'):
      ops.append(op)
      if op=='hid_pointer':stage[0]+=1
      if order=='frame-first':emit()
      m.ack(j.device,j.session,j.sequence,c['id'],True,OUT[op])
      if order=='receipt-first':time.sleep(.05);emit()
     # Sampling: a genuinely new capture of the unchanged screen while a task waits.
     if sampling and not j.done and time.monotonic()-emitted[0]>=.3:emit()
    except ValueError:pass
    time.sleep(.01)
  def vision(raw,task,verify=False):
   if verify:return dict(complete=True,verified=True,safe=True,task=task,application='设置',query='',evidence='设置标题与列表',bounds=[0,60,1000,900])
   if stage[0]==0:return dict(safe=True,complete=False,screen='桌面',action='click',target_label='设置',bounds=[100,600,200,700])
   return dict(safe=True,complete=True,screen='设置',action='unknown',target_label='设置',bounds=[0,60,1000,200])
  thread=threading.Thread(target=phone);thread.start()
  try:
   with tempfile.TemporaryDirectory() as tmp:
    n=GeneralNavigator(m,SkillStore(Path(tmp)),vision=vision,frame_timeout=.8)
    try:result=n.run(j,'打开设置')
    except ValueError as error:result=error
  finally:stop.set();thread.join()
  return ops,result,j
 def test_static_screen_with_valid_share_names_likely_causes(self):
  for order in ('receipt-first','frame-first'):
   ops,result,j=self.run_task(order)
   self.assertIsInstance(result,ValueError,order);self.assertFalse(j.navigation_verified)
   self.assertIn('屏幕共享仍有效',str(result));self.assertNotIn('请在App中共享',str(result))
   self.assertIn('未重复任何操作',str(result))
   # Waiting never adds or replays an actuator command.
   self.assertEqual(ops,['hid_home','hid_pointer'] if order=='receipt-first' else ['hid_home'])
 def test_missing_share_keeps_share_prompt(self):
  _,result,_=self.run_task(shared=False)
  self.assertIn('请在App中共享整个屏幕',str(result))
 def test_loop_completes_when_phone_samples_static_screen(self):
  for order in ('receipt-first','frame-first'):
   ops,result,j=self.run_task(order,sampling=True)
   self.assertIn('已通过画面核验完成',result,order);self.assertTrue(j.navigation_verified)
   self.assertEqual(ops,['hid_home','hid_pointer'])

class FirstFrameDiagnostics(unittest.TestCase):
 def setUp(self):
  self.authority=Authority(clock=lambda:100.0)
  self.authority_patch=patch.object(app_screen,'AUTHORITY',self.authority)
  self.authority_patch.start();self.addCleanup(self.authority_patch.stop)
  self.m=Mailbox();self.j=self.m.create('synthetic-first-frame','a'*16,1)
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.n=GeneralNavigator(self.m,SkillStore(Path(self.tmp.name)),frame_timeout=.01)
  self.ticket='t'*43
 def timeout(self):
  # No frame is emitted and no task capability is pre-bound by this helper.
  j=self.j
  before=(j.screen_session,j.command,j.result,dict(j.last_receipt),j.sequence,j.video_sequence,
          j.video_barrier,j.video,j.cancelled,j.done,j.state,j.event.is_set(),j.ui_event.is_set())
  tickets=dict(self.authority.tickets);nonces=dict(self.authority.upgrade_nonces)
  output=io.StringIO()
  with redirect_stdout(output),self.assertRaises(ValueError) as raised:self.n._frame(j,after=j.video_sequence)
  self.assertEqual(before,(j.screen_session,j.command,j.result,dict(j.last_receipt),j.sequence,j.video_sequence,
          j.video_barrier,j.video,j.cancelled,j.done,j.state,j.event.is_set(),j.ui_event.is_set()))
  self.assertEqual(tickets,self.authority.tickets);self.assertEqual(nonces,self.authority.upgrade_nonces)
  log=output.getvalue();self.assertTrue(log.startswith('FRAME_WAIT_TIMEOUT '))
  for private in (self.ticket,'replacement-ticket','private-screen-pixels','private-screen-text'):
   self.assertNotIn(private,log)
  return str(raised.exception),json.loads(log.split(' ',1)[1])
 def test_first_frame_with_device_grant_reports_unbound_not_missing_share(self):
  self.authority.tickets[self.ticket]=(200,self.j.device,'usb-screen')
  reason,event=self.timeout()
  self.assertIn('本任务尚未收到首帧',reason);self.assertIn('当前画面状态待确认',reason)
  self.assertNotIn('请在App中共享',reason);self.assertNotIn('屏幕共享仍有效',reason)
  self.assertIn('未重复任何操作',reason)
  self.assertIsNone(event['share_authorized'])
  self.assertEqual(event['share_state'],'awaiting_first_frame')
  self.assertFalse(event['screen_session_bound']);self.assertTrue(event['device_share_authorized'])
 def test_missing_expired_and_other_device_grants_keep_share_prompt(self):
  for grant in (None,(100,self.j.device,'usb-screen'),(200,'different-device','usb-screen')):
   with self.subTest(grant=grant):
    self.authority.tickets.clear()
    if grant:self.authority.tickets[self.ticket]=grant
    reason,event=self.timeout()
    self.assertIn('请在App中共享整个屏幕',reason)
    self.assertFalse(event['share_authorized']);self.assertFalse(event['device_share_authorized'])
    self.assertEqual(event['share_state'],'unavailable')
 def test_bound_active_grant_keeps_static_frame_reason_and_private_data_out_of_log(self):
  self.authority.tickets[self.ticket]=(200,self.j.device,'usb-screen')
  self.j.screen_session=self.ticket
  self.j.video=b'private-screen-pixels';self.j.reply='private-screen-text'
  self.j.video_sequence=4;self.j.video_received=self.m.clock()-3
  reason,event=self.timeout()
  self.assertIn('屏幕共享仍有效',reason)
  self.assertTrue(event['share_authorized']);self.assertTrue(event['screen_session_bound'])
  self.assertEqual(event['share_state'],'bound_authorized')
  self.assertEqual(event['after'],4);self.assertEqual(event['latest'],4)
  self.assertGreaterEqual(event['latest_age_s'],3)
 def test_bound_invalid_grant_never_adopts_a_replacement_grant(self):
  for grant in (None,(100,self.j.device,'usb-screen'),(200,'different-device','usb-screen')):
   with self.subTest(grant=grant):
    self.authority.tickets.clear()
    if grant:self.authority.tickets[self.ticket]=grant
    self.authority.tickets['replacement-ticket']=(200,self.j.device,'usb-screen')
    self.j.screen_session=self.ticket
    reason,event=self.timeout()
    self.assertIn('请在App中共享整个屏幕',reason)
    self.assertNotIn('本任务尚未收到首帧',reason)
    self.assertFalse(event['share_authorized']);self.assertTrue(event['screen_session_bound'])
    self.assertTrue(event['device_share_authorized']);self.assertEqual(event['share_state'],'bound_unavailable')

if __name__=='__main__':unittest.main()
