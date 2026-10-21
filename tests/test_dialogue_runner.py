import threading,unittest,time
from display_service.dialogue import Mailbox
from display_service.conversation import Conversation
from test_dialogue import XML
class RunnerTests(unittest.TestCase):
 def run_turn(self,decisions,outputs):
  m=Mailbox();j=m.create('d','a'*16,1);seen=[]
  def model(messages):seen.append(messages);return decisions.pop(0)
  c=Conversation(m,model,lambda text:b'\1\0'*16000,lambda *a,**kw:None)
  t=threading.Thread(target=c.run,args=(j,'打开设置'));t.start()
  while t.is_alive():
   cmd=m.poll('d','a'*16,1)
   if cmd['op'] not in ('wait','done'):m.ack('d','a'*16,1,cmd['id'],True,outputs.pop(0))
   time.sleep(.005)
  return j,seen
 def test_chat_has_no_phone_commands_and_keeps_memory(self):
  j,seen=self.run_turn([{'action':'reply','reply':'你好'}],[])
  self.assertTrue(j.done);self.assertEqual(j.reply,'你好');self.assertTrue(j.audio)
 def test_observe_before_and_after_action(self):
  j,seen=self.run_turn([{'action':'observe'},{'action':'open_settings'},{'action':'done','reply':'系统设置已打开','evidence':'设置'}],[XML,XML,XML,XML])
  self.assertEqual(j.state,'done');self.assertIn('已打开',j.reply)
 def test_unverified_completion_not_success(self):
  j,_=self.run_turn([{'action':'done','reply':'完成','evidence':'伪造'}],[])
  self.assertEqual(j.state,'error');self.assertNotEqual(j.reply,'完成')
 def test_speech_failure_does_not_claim_spoken_completion(self):
  m=Mailbox();j=m.create('d','a'*16,1)
  def failed(text):raise RuntimeError('tts unavailable')
  Conversation(m,lambda m:{'action':'reply','reply':'测试结果'},failed,lambda *a,**kw:None).run(j,'你好')
  self.assertEqual(j.state,'error');self.assertTrue(j.speech_error);self.assertEqual(j.reply,'测试结果')
