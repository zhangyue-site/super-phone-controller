"""Generic visual safety, final verification and recipe guard failures."""
import unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from display_service.general_nav import GeneralNavigator,parse_task,WORKFLOW
from display_service.dialogue import Mailbox
from display_service.skill_engine import SkillStore,signature
from test_wechat_nav import frame
class GeneralNavigationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.store=SkillStore(Path(self.temp.name));self.mailbox=Mailbox()
  self.nav=GeneralNavigator(self.mailbox,self.store,frame_timeout=.1)
 def test_bounded_drag_and_search_only_input(self):
  base=dict(safe=True,target_label='搜索',bounds=[10,10,100,100])
  command=self.nav._command(dict(base,action='drag',end=[100,800]),'打开地图搜索北京')
  self.assertEqual(set(command),{'op','kind','x','y','x2','y2','duration_ms'})
  for observation in (dict(base,action='click',target_label='支付'),dict(base,action='drag',end=[1001,10]),dict(base,action='type_text',input_focused=True,input_role='message',text='北京'),dict(base,action='type_text',input_focused=True,input_role='search',text='其他')):
   with self.assertRaises(ValueError):self.nav._command(observation,'打开地图搜索北京')
 def test_low_confidence_final_and_missing_evidence_fail(self):
  for final in ({'confidence':.94,'complete':True,'safe':True,'verified':True,'task':'打开设置','bounds':[1,1,100,100],'evidence':'设置'}, {'confidence':.99,'complete':True,'safe':True,'verified':False,'task':'打开设置','bounds':[1,1,100,100],'evidence':'设置'}, {'confidence':.99,'complete':True,'safe':True,'verified':True,'task':'打开设置','bounds':[1,1,100,100]}):
   with self.subTest(final=final):
    j=self.mailbox.create('synthetic','a'*16,1);j.pointer_protocol='absolute-v1';j.video_barrier='b'*32
    self.nav.vision=lambda raw,task,verify:final if verify else dict(confidence=.99,complete=True)
    raw=frame(0)
    with patch.object(self.nav,'_frame',return_value=(raw,1,signature(raw))),patch.object(self.nav,'_action',return_value={'op':'hid_home','ok':True,'id':'f'*32}):
     with self.assertRaises(ValueError):self.nav.run(j,'打开设置')
    self.assertFalse(j.navigation_verified);self.assertNotIn(j.device,self.store.last)
    self.mailbox.jobs.clear();self.mailbox.high.clear()
 def test_changed_result_is_independently_reverified(self):
  for application,passes in [('设置',True),('浏览器',False)]:
   with self.subTest(application=application):
    j=self.mailbox.create('synthetic','a'*16,1);j.pointer_protocol='absolute-v1';j.video_barrier='b'*32
    raw,new=frame(0),frame(1)
    valid=dict(confidence=.99,complete=True,safe=True,verified=True,task='打开设置',application='设置',bounds=[0,50,1000,900],evidence='设置页面')
    self.nav.vision=lambda data,task,verify: dict(valid,application=application) if verify and data==new else dict(valid)
    frames=[(raw,1,signature(raw)),(raw,2,signature(raw)),(new,3,signature(new))]
    with patch.object(self.nav,'_frame',side_effect=frames),patch.object(self.nav,'_action',return_value={'op':'hid_home','ok':True,'id':'f'*32}):
     if passes:self.assertIn('已通过',self.nav.run(j,'打开设置'))
     else:
      with self.assertRaises(ValueError):self.nav.run(j,'打开设置')
    self.assertEqual(j.navigation_verified,passes)
    self.assertEqual(j.device in self.store.last,passes)
    self.mailbox.jobs.clear();self.mailbox.high.clear()
 def test_observation_waits_beyond_receipt_frame(self):
  j=self.mailbox.create('synthetic','a'*16,1);j.pointer_protocol='absolute-v1';j.video_barrier='b'*32
  raw=frame(0);valid=dict(confidence=.99,complete=True,safe=True,verified=True,task='打开设置',application='设置',bounds=[0,50,1000,900],evidence='设置页面')
  self.nav.vision=lambda *args:dict(valid)
  def action(*args):
   j.video_sequence=10
   return {'op':'hid_home','ok':True,'id':'f'*32}
  with patch.object(self.nav,'_frame',side_effect=[(raw,1,signature(raw)),(raw,11,signature(raw)),(raw,12,signature(raw))]) as frames,patch.object(self.nav,'_action',side_effect=action):
   self.nav.run(j,'打开设置')
  self.assertEqual(frames.call_args_list[1].kwargs,{'after':10})
  self.assertEqual(frames.call_args_list[2].kwargs,{'after':11})
 def test_unknown_action_requires_independent_goal_verification(self):
  for app,passes in [('设置',True),('浏览器',False)]:
   with self.subTest(app=app):
    j=self.mailbox.create('synthetic','a'*16,1);j.pointer_protocol='absolute-v1';j.video_barrier='b'*32
    raw=frame(0)
    final=dict(confidence=.99,complete=True,safe=True,verified=True,task='打开设置',application=app,bounds=[0,50,1000,900],evidence='可见应用页面')
    self.nav.vision=lambda data,task,verify:final if verify else dict(confidence=.95,safe=True,action='unknown',screen='设置页面')
    with patch.object(self.nav,'_frame',return_value=(raw,1,signature(raw))),patch.object(self.nav,'_action',return_value={'op':'hid_home','ok':True}) as actions:
     if passes:self.nav.run(j,'打开设置')
     else:
      with self.assertRaises(ValueError):self.nav.run(j,'打开设置')
     actions.assert_called_once()
    self.assertEqual(j.navigation_verified,passes)
    self.mailbox.jobs.clear();self.mailbox.high.clear()
 def test_general_method_binds_new_safe_goal_without_old_coordinates(self):
  job=SimpleNamespace(device='synthetic',done=True,state='done',navigation_verified=True)
  raw=frame(0);steps=[{'signature':signature(raw),'target':{},'receipt':{'id':'a'*32,'op':'hid_pointer','ok':True}}]
  self.store.remember(job,WORKFLOW,{'task':'打开地图搜索北京'},steps,(240,480),{'op':'hid_home','ok':True},{'verified':True,'terminal':WORKFLOW.terminal,'parameters':{'task':'打开地图搜索北京'}})
  self.store.save_last(job.device)
  method=self.store.find(job.device,WORKFLOW,{'task':'打开浏览器搜索天气'})
  self.assertEqual(method['executionMode'],'semantic');self.assertNotIn('steps',method)
  card=self.store.cards(job.device)[0]
  with self.assertRaises(ValueError):self.store.resolve('other-device',card['id'],{})
  self.assertEqual(self.store.resolve(job.device,card['id'],{'task':'打开地图搜索上海'}),'打开地图搜索上海')
  with self.assertRaises(ValueError):self.store.resolve(job.device,card['id'],{'task':'删除地图数据'})
if __name__=='__main__':unittest.main()
