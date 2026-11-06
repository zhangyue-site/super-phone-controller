import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from display_service.general_nav import GeneralNavigator,WORKFLOW
from display_service.dialogue import Mailbox
from display_service.skill_engine import SkillStore,signature,region
from test_wechat_nav import frame

class SemanticNavigationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.store=SkillStore(Path(self.tmp.name));self.raw=frame(0)
 def remember(self,steps=None,task='打开设置'):
  j=SimpleNamespace(device='synthetic',done=True,state='done',navigation_verified=True,sequence=1)
  if steps is None:steps=[{'signature':signature(self.raw),'target':region(self.raw,[10,100,100,200]),'observation':{'bounds':[10,100,100,200],'target_label':'设置'},'receipt':{'op':'hid_pointer','id':'a'*32,'ok':True}}]
  self.store.remember(j,WORKFLOW,{'task':task},steps,(240,480),{'op':'hid_home','id':'b'*32,'ok':True},{'verified':True,'terminal':WORKFLOW.terminal,'parameters':{'task':task}})
  self.store.save_last(j.device);return self.store.cards(j.device)[0]['id']
 def test_saved_method_has_no_coordinate_or_image_replay(self):
  ident=self.remember();entry=json.loads(self.store._path('synthetic').read_text())['skills'][ident]
  self.assertEqual(entry['executionMode'],'semantic');self.assertFalse(entry['method']['coordinateReplay'])
  self.assertNotIn('steps',entry)
  for key in ('geometry','signature','pixels','bounds','target'):
   self.assertNotIn('"'+key+'"',json.dumps(entry))
 def test_same_method_can_bind_a_new_safe_app(self):
  ident=self.remember();self.assertEqual(self.store.resolve('synthetic',ident,{'task':'打开相机'}),'打开相机')
  method=self.store.find('synthetic',WORKFLOW,{'task':'打开相机'});self.assertEqual(method['executionMode'],'semantic');self.assertNotIn('steps',method)
 def test_new_target_cannot_turn_method_into_destructive_action(self):
  ident=self.remember()
  for task in ('删除照片','打开设置并卸载应用','发送消息给测试联系人','shell reboot'):
   with self.subTest(task=task),self.assertRaises(ValueError):self.store.resolve('synthetic',ident,{'task':task})
 def test_home_key_method_can_be_saved_without_pointer_steps(self):
  ident=self.remember([],task='回到手机桌面');self.assertEqual(self.store.resolve('synthetic',ident,{}),'回到手机桌面')
 def test_legacy_coordinate_skill_resolves_as_semantic_without_replay(self):
  ident=self.remember();p=self.store._path('synthetic');d=json.loads(p.read_text());e=d['skills'][ident];e.pop('executionMode');e.pop('method');e['steps']=[{'observation':{'bounds':[1,2,30,40]}}];p.write_text(json.dumps(d))
  self.assertEqual(self.store.resolve('synthetic',ident,{'task':'打开相机'}),'打开相机');self.assertNotIn('steps',self.store.find('synthetic',WORKFLOW,{'task':'打开相机'}))
 def test_five_icon_positions_always_use_current_visual_observation(self):
  positions=[[50,100,150,200],[700,100,800,200],[300,400,400,500],[50,700,150,800],[700,700,800,800]]
  for index,box in enumerate(positions):
   with self.subTest(box=box):
    m=Mailbox();j=m.create('synthetic','a'*16,index+1);j.pointer_protocol='absolute-v1';j.video_barrier='b'*32
    nav=GeneralNavigator(m,self.store,frame_timeout=.1);seen=[];commands=[]
    good=dict(confidence=.99,safe=True,complete=True,verified=True,task='打开设置',application='设置',bounds=[0,50,1000,900],evidence='系统设置页')
    def vision(raw,task,verify):
     seen.append(verify)
     if verify:return dict(good)
     return dict(good) if len(seen)>1 else dict(confidence=.99,safe=True,complete=False,screen='应用抽屉',action='click',target_label='设置',bounds=box)
    nav.vision=vision
    def action(job,command,expected):commands.append(command);return {'id':'c'*32,'ok':True,'op':command['op']}
    with patch.object(self.store,'find',side_effect=AssertionError('old coordinate skill must not be used')),patch('display_service.skill_engine.ReplayEngine.step',side_effect=AssertionError('coordinate replay forbidden')),patch.object(nav,'_frame',return_value=(self.raw,1,signature(self.raw))),patch.object(nav,'_action',side_effect=action):nav.run(j,'打开设置')
    click=commands[1];self.assertEqual(click['x'],(box[0]+box[2])*32767//2000);self.assertEqual(click['y'],(box[1]+box[3])*32767//2000);self.assertTrue(j.navigation_verified)
