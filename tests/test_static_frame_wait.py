"""Synthetic phone that, like Android ImageReader, uploads only on screen change.

Not evidence of a real phone, lock screen, or the experimental sampling path.
"""
import tempfile,threading,time,unittest
from pathlib import Path
from display_service import app_screen
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
if __name__=='__main__':unittest.main()
