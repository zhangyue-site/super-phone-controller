"""Synthetic integration, not evidence of a real phone or HID endpoint."""
import tempfile,threading,time,unittest
from pathlib import Path
from display_service.dialogue import Mailbox
from display_service.general_nav import GeneralNavigator
from display_service.skill_engine import SkillStore
from test_wechat_nav import frame
class UsbPinyinFlow(unittest.TestCase):
 def flow(self,bad=False,cancel=False):
  m=Mailbox();j=m.create('synthetic','a'*16,1);j.pointer_protocol='absolute-v1';j.video_source='user-consented-app-screen'
  stage=[0];commands=[];stop=threading.Event()
  def feed():
   while not stop.is_set():
    try:
     c=m.poll(j.device,j.session,j.sequence,'absolute-v1');op=c['op']
     if op not in ('wait','done'):
      commands.append(op)
      if op=='hid_home':out='HID_HOME_REPORT_SENT'
      elif op=='hid_text':
       self.assertEqual(c['text'],'beijing');stage[0]=1;out='HID_TEXT_REPORT_SENT'
      elif op=='hid_pointer':stage[0]=2;out='HID_POINTER_REPORT_SENT'
      else:raise AssertionError('non-USB op '+op)
      m.ack(j.device,j.session,j.sequence,c['id'],True,out)
      if cancel and op=='hid_text':m.cancel(j.device)
     m.ingest_video(j.device,j.session,j.sequence,j.video_sequence+1,frame(stage[0]),'jpeg',expected_barrier=j.video_barrier,source='user-consented-app-screen')
    except ValueError:pass
    time.sleep(.01)
  def vision(raw,task,verify=False):
   base=dict(safe=True,input_visible=True,input_focused=True,input_role='search',input_password=False,bounds=[100,80,800,150],target_label='搜索框',complete=False)
   if stage[0]==0:return dict(base,action='type_text',text='北京')
   if stage[0]==1:return dict(base,action='click',committed_text='',candidates=[dict(text='北京',bounds=[100,600,300,700])])
   return dict(base,action='unknown',committed_text='背景' if bad else '北京',complete=True,verified=True,task=task,query='北京',evidence='搜索框与结果显示北京',application='设置')
  thread=threading.Thread(target=feed);thread.start()
  try:
   with tempfile.TemporaryDirectory() as tmp:
    n=GeneralNavigator(m,SkillStore(Path(tmp)),vision=vision,frame_timeout=.8)
    if bad or cancel:
     with self.assertRaises(ValueError):n.run(j,'搜索北京')
     self.assertFalse(j.navigation_verified)
    else:
     self.assertIn('已通过',n.run(j,'搜索北京'));self.assertTrue(j.navigation_verified)
  finally:stop.set();thread.join()
  return commands
 def test_full_synthetic_usb_pinyin_candidate_and_verification(self):self.assertEqual(self.flow(),['hid_home','hid_text','hid_pointer'])
 def test_wrong_candidate_commit_fails(self):self.assertEqual(self.flow(bad=True),['hid_home','hid_text','hid_pointer'])
 def test_stop_after_typing_never_selects_candidate(self):self.assertEqual(self.flow(cancel=True),['hid_home','hid_text'])
if __name__=='__main__':unittest.main()
