import threading,unittest,time
from display_service.dialogue import Mailbox
from display_service.conversation import Conversation
from test_dialogue import XML
class RunnerTests(unittest.TestCase):
 def run_turn(self,decisions,outputs,task="打开设置"):
  m=Mailbox();j=m.create('d','a'*16,1);seen=[]
  def model(messages):seen.append(messages);return decisions.pop(0)
  c=Conversation(m,model,lambda text:b'\1\0'*16000,lambda *a,**kw:None)
  t=threading.Thread(target=c.run,args=(j,task));t.start()
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
  j,_=self.run_turn([{'action':'done','reply':'完成','evidence':'伪造'}],[XML])
  self.assertEqual(j.state,'error');self.assertNotEqual(j.reply,'完成')
 def test_speech_failure_does_not_claim_spoken_completion(self):
  m=Mailbox();j=m.create('d','a'*16,1)
  def failed(text):raise RuntimeError('tts unavailable')
  Conversation(m,lambda m:{'action':'reply','reply':'测试结果'},failed,lambda *a,**kw:None).run(j,'你好')
  self.assertEqual(j.state,'error');self.assertTrue(j.speech_error);self.assertEqual(j.reply,'测试结果')

 def test_launched_app_must_remain_foreground_after_navigation(self):
  initial=XML.replace('SIZE 1080x2400','SIZE 1080x2400\nAPPS_BEGIN\ncom.example.app/.MainActivity\nAPPS_END')
  current=XML.replace('com.android.settings','com.example.app').replace('text="设置"','text="账单"')
  foreign=current.replace('com.example.app','com.unexpected.app')
  j,_=self.run_turn([{'action':'observe'},{'action':'launch','component':'com.example.app/.MainActivity'},{'action':'tap','node':0},{'action':'done','reply':'已完成','evidence':'账单'}],[initial,initial,'ok',current,current,'ok',foreign],task='打开账单应用')
  self.assertEqual(j.state,'error')
 def test_incorrect_completion_quote_can_be_corrected_without_replaying_input(self):
  j,seen=self.run_turn([{'action':'observe'},{'action':'open_settings'},{'action':'done','reply':'已打开','evidence':'系统设置'},{'action':'done','reply':'已打开','evidence':'设置'}],[XML,XML,'ok',XML])
  self.assertEqual(j.state,'done');self.assertEqual(len(seen),4)
 def test_null_reply_is_rejected_and_repaired_before_speaking(self):
  j,seen=self.run_turn([{'action':'reply','reply':None},{'action':'reply','reply':'你叫小乐'}],[])
  self.assertEqual(j.state,'done');self.assertEqual(j.reply,'你叫小乐');self.assertEqual(len(seen),2)

 def test_phone_command_without_observation_first_reads_and_replans(self):
  initial=XML.replace('SIZE 1080x2400','SIZE 1080x2400\nAPPS_BEGIN\ncom.example.app/.MainActivity\nAPPS_END')
  current=XML.replace('com.android.settings','com.example.app').replace('text="设置"','text="账单"')
  j,_=self.run_turn([{'action':'launch','component':'com.guessed/.Wrong'},{'action':'launch','component':'com.example.app/.MainActivity'},{'action':'done','reply':'已打开','evidence':'账单'}],[initial,initial,'ok',current],task='打开账单应用')
  self.assertEqual(j.state,'done')
