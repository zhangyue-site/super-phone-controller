"""Synthetic integration, not evidence of a real phone, IME or HID endpoint."""
import json,tempfile,threading,time,unittest
from pathlib import Path
from unittest import mock
from display_service import general_vision
from display_service.dialogue import Mailbox
from display_service.general_nav import GeneralNavigator,MAX_SAME_CLICKS,_repeated_clicks
from display_service.keyboard_navigation import ImeLatinCommit,decision
from display_service.skill_engine import SkillStore
from test_wechat_nav import frame
SEARCH=dict(safe=True,complete=False,screen='设置',target_label='搜索设置',bounds=[60,90,940,150])
def focus(**kw):return dict(input_visible=True,input_focused=True,input_role='search',input_password=False,safe=True,**kw)
class NavigationHistory(unittest.TestCase):
 def flow(self,vision,task='打开设置搜索北京'):
  m=Mailbox();j=m.create('synthetic','a'*16,1);j.pointer_protocol='absolute-v1';j.video_source='user-consented-app-screen'
  commands=[];stop=threading.Event()
  def feed():
   while not stop.is_set():
    try:
     c=m.poll(j.device,j.session,j.sequence,'absolute-v1');op=c['op']
     if op not in ('wait','done'):
      commands.append(op)
      m.ack(j.device,j.session,j.sequence,c['id'],True,dict(hid_home='HID_HOME_REPORT_SENT',hid_pointer='HID_POINTER_REPORT_SENT',hid_text='HID_TEXT_REPORT_SENT')[op])
     m.ingest_video(j.device,j.session,j.sequence,j.video_sequence+1,frame(0),'jpeg',expected_barrier=j.video_barrier,source='user-consented-app-screen')
    except ValueError:pass
    time.sleep(.01)
  thread=threading.Thread(target=feed);thread.start()
  try:
   with tempfile.TemporaryDirectory() as tmp:
    n=GeneralNavigator(m,SkillStore(Path(tmp)),vision=vision,frame_timeout=.8)
    try:result=n.run(j,task)
    except ValueError as error:result=error
  finally:stop.set();thread.join()
  return commands,result,j
 def test_repeated_search_bar_click_stops_before_third_dispatch(self):
  # Physical-keyboard mode: no soft keyboard, the planner keeps proposing the bar.
  seen=[]
  def vision(raw,task,verify=False):
   seen.append(general_vision._ACKED_STEPS.get())
   return dict(SEARCH,action='click',input_visible=True,input_focused=False,input_role='search',input_password=False)
  commands,result,j=self.flow(vision)
  self.assertEqual(commands,['hid_home']+['hid_pointer']*MAX_SAME_CLICKS)
  self.assertIsInstance(result,ValueError);self.assertIn('同一目标',str(result));self.assertFalse(j.navigation_verified)
  self.assertEqual(seen[0],({'step':1,'op':'hid_home'},))
  self.assertEqual(seen[1][-1],{'step':2,'op':'hid_pointer','kind':'click','screen':'设置','target_label':'搜索设置'})
  self.assertTrue(all('center' not in s for steps in seen for s in steps))
 def test_click_then_focused_search_enters_pinyin_loop(self):
  def vision(raw,task,verify=False):
   steps=general_vision._ACKED_STEPS.get()
   if verify:return dict(complete=True,verified=True,safe=True,task=task,application='设置',query='北京',evidence='搜索框与结果显示北京',bounds=[60,90,940,600])
   if len(steps)==1:return dict(SEARCH,action='click')
   if len(steps)==2:return dict(SEARCH,**focus(action='type_text',text='北京',screen='搜索设置'))
   if len(steps)==3:return dict(SEARCH,**focus(action='click',committed_text='',candidates=[dict(text='北京',bounds=[100,600,300,700])]))
   return dict(SEARCH,**focus(action='unknown',committed_text='北京',complete=True))
  commands,result,j=self.flow(vision)
  self.assertEqual(commands,['hid_home','hid_pointer','hid_text','hid_pointer'])
  self.assertIn('已通过',result);self.assertTrue(j.navigation_verified)
 def test_same_position_different_label_is_not_a_repeat(self):
  steps=[dict(kind='click',target_label='网络和互联网',center=(500,300))]
  self.assertEqual(_repeated_clicks(steps,dict(target_label='WLAN',bounds=[0,280,1000,320])),0)
  self.assertEqual(_repeated_clicks(steps,dict(target_label='网络和互联网',bounds=[0,280,1000,330])),1)
  self.assertEqual(_repeated_clicks(steps+[dict(kind='click',target_label=None,center=(500,300))],dict(target_label='网络和互联网',bounds=[0,280,1000,330])),1)
 def test_latin_commit_is_reported_and_never_retyped(self):
  _,plan,_=decision(None,focus(action='type_text',text='北京'),'搜索北京',2)
  for committed in ('beijing','bei jing',"bei'jing",'Beijing'):
   with self.assertRaises(ImeLatinCommit):decision(plan,focus(committed_text=committed,candidates=[]),'搜索北京',3)
  command,selection,_=decision(plan,focus(committed_text='beijing',candidates=[dict(text='北京',bounds=[10,600,200,700])]),'搜索北京',3)
  self.assertEqual(command['op'],'hid_pointer');self.assertEqual(selection['stage'],'select_candidate')
  _,ascii_plan,_=decision(None,focus(action='type_text',text='wifi'),'搜索wifi',2)
  _,done,observe_only=decision(ascii_plan,focus(committed_text='wifi'),'搜索wifi',3)
  self.assertTrue(observe_only);self.assertTrue(done['verified'])
 def test_history_reaches_planner_prompt_but_not_verifier(self):
  payloads=[]
  def fake_request(payload,provider,model,cfg):
   payloads.append(payload)
   content=json.dumps(dict(coordinate_system='pixels',safe=True,complete=False,action='unknown'))
   return {'choices':[{'message':{'content':content},'finish_reason':'stop'}]},mock.Mock(get_header=lambda k:None),provider,time.monotonic()
  with mock.patch.object(general_vision,'request_vision',fake_request),mock.patch.object(general_vision,'vision_route',lambda:('fake','model',{})):
   with general_vision.acked_steps([dict(step=1,op='hid_home'),dict(step=2,op='hid_pointer',kind='click',screen='设置',target_label='搜索设置',center=(500,120))]):
    general_vision.observe(frame(0),'打开设置搜索北京')
    general_vision.observe(frame(0),'打开设置搜索北京',verify=True)
   general_vision.observe(frame(0),'打开设置搜索北京')
  planner,verifier,later=(p['messages'][1]['content'][0]['text'] for p in payloads)
  self.assertIn('acked_steps=',planner);self.assertIn('搜索设置',planner);self.assertNotIn('center',planner)
  self.assertNotIn('acked_steps',verifier);self.assertNotIn('acked_steps',later)
if __name__=='__main__':unittest.main()
