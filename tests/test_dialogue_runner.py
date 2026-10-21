import threading,unittest,time
from unittest.mock import patch
from display_service.dialogue import Mailbox
from display_service.conversation import Conversation
class RunnerTests(unittest.TestCase):
 def run_turn(self,decision,backend='hid_pending'):
  m=Mailbox();j=m.create('d','a'*16,1)
  def forbidden(*a,**kw):raise AssertionError('phone action must stay disabled')
  m.execute=forbidden
  with patch.dict('os.environ',{'EPAPER_PHONE_BACKEND':backend}):
   Conversation(m,lambda messages:decision,lambda text:b'\1\0'*16000,lambda *a,**kw:None).run(j,'打开微信找到李洋')
  return j
 def test_chat_runs_without_phone_actions_and_keeps_memory(self):
  m=Mailbox();j=m.create('d','a'*16,1)
  c=Conversation(m,lambda messages:{'action':'reply','reply':'你好'},lambda text:b'\1\0'*16000,lambda *a,**kw:None)
  c.run(j,'你好')
  self.assertTrue(j.done);self.assertEqual(j.reply,'你好');self.assertTrue(j.audio)
 def test_phone_action_is_blocked_without_executing_any_mailbox_command(self):
  for backend in ('hid_pending','autoglm','legacy',''):
   with self.subTest(backend=backend):
    j=self.run_turn({'action':'observe'},backend)
    self.assertEqual(j.state,'error');self.assertIn('尚未接入',j.reply);self.assertTrue(j.audio)
 def test_done_action_cannot_claim_phone_result_without_video(self):
  j=self.run_turn({'action':'done','reply':'已找到李洋','evidence':'李洋'})
  self.assertEqual(j.state,'error');self.assertIn('当前没有执行',j.reply)
 def test_stop_is_spoken(self):
  j=self.run_turn({'action':'stop','reply':'操作已停止'})
  self.assertEqual(j.state,'done');self.assertEqual(j.reply,'操作已停止')
 def test_speech_failure_does_not_claim_spoken_completion(self):
  m=Mailbox();j=m.create('d','a'*16,1)
  def failed(text):raise RuntimeError('tts unavailable')
  Conversation(m,lambda m:{'action':'reply','reply':'测试结果'},failed,lambda *a,**kw:None).run(j,'你好')
  self.assertEqual(j.state,'error');self.assertTrue(j.speech_error);self.assertEqual(j.reply,'测试结果')
 def test_active_turn_survives_expiry_sweep(self):
  now=[0];m=Mailbox(clock=lambda:now[0]);j=m.create('d','a'*16,1);c=Conversation(m,status=lambda *a,**kw:None)
  now[0]=10;c.expire();self.assertFalse(j.cancelled)
  now[0]=46;c.expire();self.assertTrue(j.cancelled)
