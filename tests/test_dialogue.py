import unittest
from display_service import dialogue
XML='''FOCUS com.android.settings/.Settings
LOCKED false
SIZE 1080x2400
<?xml version="1.0"?><hierarchy><node package="com.android.settings" text="设置" clickable="true" enabled="true" bounds="[0,0][200,200]"/><node package="com.android.settings" text="删除所有数据" clickable="true" bounds="[0,200][200,400]"/><node text="secret" password="true" bounds="[0,400][200,600]"/></hierarchy>
END_FOCUS com.android.settings/.Settings
END_LOCKED false'''
class DialogueTests(unittest.TestCase):
 def test_observation_and_typed_navigation(self):
  obs=dialogue.parse_observation(XML)
  self.assertEqual(obs['package'],'com.android.settings')
  self.assertFalse(any('secret' in str(n) for n in obs['nodes']))
  self.assertEqual(dialogue.action_command({'action':'tap','node':0},obs),{'op':'tap','x':100,'y':100})
  with self.assertRaises(ValueError):dialogue.action_command({'action':'tap','node':1},obs)
 def test_locked_or_incomplete_observation_rejected(self):
  for raw in [XML.replace('LOCKED false','LOCKED true'),XML[:150],XML.replace('FOCUS com.android.settings/.Settings','FOCUS unknown'),XML.replace('END_LOCKED false','END_LOCKED true')]:
   with self.assertRaises(ValueError):dialogue.parse_observation(raw)
 def test_mailbox_no_redelivery_and_stale_ack(self):
  now=[0];m=dialogue.Mailbox(clock=lambda:now[0]);j=m.create('one','a'*16,1)
  m.offer(j,{'op':'home'});cmd=m.poll('one','a'*16,1)
  self.assertEqual(cmd['op'],'home');self.assertEqual(m.poll('one','a'*16,1)['op'],'wait')
  with self.assertRaises(ValueError):m.ack('one','b'*16,1,cmd['id'],True,'ok')
  m.ack('one','a'*16,1,cmd['id'],True,'ok')
  with self.assertRaises(ValueError):m.ack('one','a'*16,1,cmd['id'],True,'ok')
 def test_cancel_is_device_scoped_and_new_turn_not_replaced(self):
  m=dialogue.Mailbox();j=m.create('one','a'*16,1);other=m.create('two','a'*16,1)
  m.cancel('one');self.assertTrue(j.cancelled);self.assertFalse(other.cancelled)
  with self.assertRaises(ValueError):m.offer(j,{'op':'home'})
 def test_expired_or_duplicate_turn_cannot_start(self):
  now=[0];m=dialogue.Mailbox(clock=lambda:now[0]);j=m.create('one','a'*16,1)
  with self.assertRaises(ValueError):m.create('one','a'*16,1)
  now[0]=16
  with self.assertRaises(ValueError):m.offer(j,{'op':'home'})
 def test_completion_requires_current_evidence(self):
  obs=dialogue.parse_observation(XML)
  self.assertTrue(dialogue.verify_done('打开设置',{'evidence':'设置'},obs))
  self.assertFalse(dialogue.verify_done('打开设置',{'evidence':'不存在'},obs))
  self.assertFalse(dialogue.verify_done('回到桌面',{'evidence':'设置'},obs))
