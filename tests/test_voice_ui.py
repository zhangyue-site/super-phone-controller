import io,json,os,threading,time,unittest
from unittest.mock import patch,Mock
from display_service.dialogue import Mailbox
from display_service.conversation import Conversation
from display_service import voice_ui
from display_service.render import render_voice_ui

class VoiceUITests(unittest.TestCase):
 def setUp(self):
  self.env=patch.dict(os.environ,{'EPAPER_VOICE_UI':'1','EPAPER_WECHAT_NAV':'1'});self.env.start();self.addCleanup(self.env.stop)
  self.m=Mailbox();self.calls=[]
  self.nav=Mock()
  def run(j,text):self.calls.append(text);j.navigation_verified=True;return '已通过画面核验完成：'+text
  self.nav.run.side_effect=run
  self.c=Conversation(mailbox=self.m,tts=lambda _:b'\0\0'*100,status=lambda *a:None,general_navigator=self.nav,planner=lambda _:['先回手机桌面','按画面寻找并打开','核对最终画面'])
 def start(self,protocol='plan-v1'):
  j=self.m.create('synthetic','a'*16,1);j.ui_protocol=protocol;t=threading.Thread(target=self.c.run,args=(j,'打开计算器'));t.start();self.addCleanup(lambda:t.join(2));return j,t
 def wait_plan(self,j):
  until=time.monotonic()+2
  while j.state!='plan' and time.monotonic()<until:time.sleep(.005)
  self.assertEqual(j.state,'plan')
 def test_no_phone_action_until_matching_screen_receipt(self):
  j,t=self.start();self.wait_plan(j);self.assertFalse(self.calls);self.assertEqual(j.ui_heard,'打开计算器');revision=j.ui_revision
  with self.assertRaises(ValueError):self.m.ui_seen(j.device,j.session,j.sequence,revision-1)
  self.assertFalse(self.calls)
  self.m.ui_seen(j.device,j.session,j.sequence,revision);t.join(2);self.assertFalse(t.is_alive());self.assertEqual(self.calls,['打开计算器']);self.assertEqual(j.state,'done')
 def test_stop_while_reading_plan_never_dispatches(self):
  j,t=self.start();self.wait_plan(j);self.m.cancel(j.device);t.join(2);self.assertFalse(self.calls);self.assertTrue(j.cancelled)
 def test_preview_timeout_is_fail_closed(self):
  j=self.m.create('synthetic','b'*16,2);j.ui_protocol='plan-v1'
  with self.assertRaisesRegex(ValueError,'未操作手机'):voice_ui.preview(self.m,j,'打开计算器',lambda _:['先回手机桌面'],timeout=.02)
  self.assertFalse(self.calls)
 def test_old_firmware_keeps_existing_flow_without_waiting(self):
  self.c.planner=Mock(side_effect=AssertionError('old firmware must not require UI ack'))
  j,t=self.start(protocol='');t.join(2);self.assertEqual(self.calls,['打开计算器']);self.c.planner.assert_not_called()
 def test_future_bool_wrong_turn_and_old_protocol_receipts_rejected(self):
  j=self.m.create('synthetic','c'*16,3);j.ui_protocol='plan-v1';j.ui_revision=2
  for revision in (True,0,3):
   with self.subTest(revision=revision),self.assertRaises(ValueError):self.m.ui_seen(j.device,j.session,j.sequence,revision)
  with self.assertRaises(ValueError):self.m.ui_seen(j.device,'d'*16,j.sequence,2)
  j.ui_protocol=''
  with self.assertRaises(ValueError):self.m.ui_seen(j.device,j.session,j.sequence,2)
 def test_ui_revision_only_advertised_for_capable_clients(self):
  j=self.m.create('synthetic','e'*16,4);self.assertNotIn('uiRevision',self.m.poll(j.device,j.session,j.sequence));j.ui_protocol='plan-v1';j.ui_revision=2;self.assertEqual(self.m.poll(j.device,j.session,j.sequence)['uiRevision'],2)
 def test_model_plan_cannot_add_actions_or_change_goal(self):
  cfg={'baseUrl':'https://synthetic.invalid/v1','apiKey':'synthetic-only'}
  for result in ({'goal':'打开计算器','steps':['home','pay']},{'goal':'打开其他应用','steps':['home','locate_open_app','verify']}):
   raw={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}]}
   with patch.object(voice_ui,'vision_route',return_value=('opencode-go','mimo-v2.6-flash',cfg)),patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(raw).encode())):
    self.assertEqual(voice_ui.plan_navigation('打开计算器'),['先回手机桌面','按画面寻找并打开','核对最终画面'])
 def test_small_screen_frames_have_fixed_dimensions_and_stop_target(self):
  j=self.m.create('synthetic','f'*16,5);j.ui_heard='打开计算器，再核对结果';j.ui_plan=['先回手机桌面','按画面寻找并打开','核对最终画面']
  for state in ('planning','plan','running'):
   j.state=state;im=render_voice_ui(j);self.assertEqual((im.size,len(im.tobytes())),((200,200),5000));self.assertEqual(im.getpixel((8,132)),0)

 def test_ordinary_chat_also_echoes_heard_text_and_keeps_it_in_final(self):
  release=threading.Event()
  self.c.model=lambda _:(release.wait(2) or True) and {'action':'reply','reply':'你好，我听到了。'}
  j=self.m.create('synthetic','1'*16,6);j.ui_protocol='plan-v1'
  t=threading.Thread(target=self.c.run,args=(j,'你好'));t.start()
  try:
   until=time.monotonic()+1
   while j.ui_revision==0 and time.monotonic()<until:time.sleep(.005)
   self.assertEqual(j.ui_heard,'你好');self.assertEqual(j.state,'planning');self.assertFalse(self.calls)
  finally:release.set();t.join(2)
  self.assertEqual(j.state,'done');self.assertEqual(j.ui_heard,'你好');self.assertEqual(len(render_voice_ui(j).tobytes()),5000)

 def test_pointer_wire_packet_preserves_strict_firmware_allowlist(self):
  j=self.m.create('synthetic','2'*16,7);j.ui_protocol='plan-v1';j.ui_revision=3
  command={'op':'hid_pointer','kind':'drag','x':16383,'y':21298,'x2':16383,'y2':8191,'duration_ms':600}
  self.m.offer(j,command);packet=self.m.poll(j.device,j.session,j.sequence)
  self.assertEqual(set(packet),set(command)|{'id'});self.assertEqual(len(packet['id']),32)
  self.assertEqual(self.m.poll(j.device,j.session,j.sequence)['uiRevision'],3)
