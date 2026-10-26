"""Real HTTP synthetic A relay; no physical phone or BLE claims."""
import unittest,uuid,time,hashlib,hmac
from unittest.mock import patch
from test_wechat_nav import frame
from display_service.general_nav import GeneralNavigator
from display_service import app_screen
from display_service import remote_http
from test_remote_http import RemoteHttpTests

class BoardControlTests(RemoteHttpTests):
 test_both_origins_real_http_flow_and_scoped_verified_result=None
 test_bridge_auth_unknown_peer_cross_confirmation_and_stop=None
 test_remote_stop_blocks_voice_asr_already_in_flight=None
 def setUp(self):
  super().setUp()
  from display_service import board_control
  from unittest.mock import patch
  self.bp=patch.object(board_control,"SESSIONS",board_control.Sessions());self.bp.start()
  self.remote.binding_allowed=remote_http.binding_allowed
 def tearDown(self):
  self.bp.stop();super().tearDown()
 def command(self,operation,session='a'*32,request_id=None,**values):
  return self.request('/board-control',dict(session=session,request_id=request_id or uuid.uuid4().hex,operation=operation,**values))
 def test_skill_metadata_capacity_is_explicit_and_idempotent(self):
  ident=uuid.uuid4().hex
  with patch.object(self.skills,'cards',return_value=[{'description':'天气'*5000}]) as cards:
   first=self.command('skills',request_id=ident)
   self.assertEqual(first[0],409)
   self.assertIn('容量',first[1]['reply'])
   self.assertLess(len(__import__('json').dumps(first[1],ensure_ascii=False).encode()),7800)
   self.assertEqual(self.command('skills',request_id=ident),first)
   self.assertEqual(cards.call_count,1)
 def test_retirement_rejects_late_confirm_and_single_frame_replay(self):
  old='c'*32
  _,plan=self.command('prepare',session=old,text='打开浏览器搜索天气')
  self.assertEqual(self.command('disconnect',session=old)[0],200)
  self.assertEqual(self.command('confirm',session=old,task_id=plan['task_id'])[0],403)
  self.assertEqual(self.command('prepare',session=old,text='打开地图搜索北京')[0],403)
  self.assertEqual(self.command('prepare',session='d'*32,text='打开地图搜索北京')[0],200)
 def test_usb_domain_and_serial_isolation(self):
  serial='AABBCCDDEEFF'
  code,c=self.request('/app-screen/usb-challenge',{'device':'epaper-01','serial':serial});self.assertEqual(code,200)
  proof=hmac.new(b'synthetic-device-only',b'pcusb-v1\n'+b'epaper-01\n'+serial.encode()+b'\n'+bytes.fromhex(c['challenge']),hashlib.sha256).hexdigest()
  code,g=self.request('/app-screen/usb-authorize',dict(device='epaper-01',serial=serial,challenge=c['challenge'],proof=proof))
  self.assertEqual(code,200);self.assertEqual(g['serial'],serial)
  self.assertEqual(self.request('/app-screen/status',extra={'Authorization':'Bearer '+g['ticket']})[0],200)
  _,c=self.request('/app-screen/usb-challenge',{'device':'epaper-01','serial':serial})
  old=hmac.new(b'synthetic-device-only',b'PCFLASH1\nepaper-01\n'+bytes.fromhex(c['challenge']),hashlib.sha256).hexdigest()
  self.assertEqual(self.request('/app-screen/usb-authorize',dict(device='epaper-01',serial=serial,challenge=c['challenge'],proof=old))[0],403)
 def test_generic_visual_http_receipts_and_skill_launch(self):
  for task in ('打开浏览器搜索天气','打开地图搜索北京','打开浏览器搜索天气'):
   with self.subTest(task=task):
    self.stage=0;calls=[]
    def vision(raw,query,verify=False):
     calls.append(verify)
     base=dict(confidence=.99,safe=True,screen='synthetic',target_label='搜索',input_role='search',bounds=[100,100,300,200])
     if verify:return dict(base,complete=True,verified=True,task=query,evidence=query,application=query[2:].split("搜索")[0],query=query.split("搜索")[-1])
     if self.stage>=3:return dict(base,complete=True)
     if self.stage==2:return dict(base,action='type_text',input_focused=True,text=query[-2:])
     return dict(base,action='click')
    self.c.general_navigator=GeneralNavigator(self.mailbox,self.skills,vision=vision,frame_timeout=2)
    cards=self.command('skills')[1]['skills']
    card=next((c for c in cards if c['parameters'][0]['value']==task),cards[0] if cards else None)
    code,plan=self.command('skill',skill_id=card['id'],parameters={'task':task}) if card else self.command('prepare',text=task)
    self.assertEqual(code,200)
    self.assertEqual(self.command('confirm',task_id=plan['task_id'])[1]['state'],'queued')
    self.request('/remote/claim',{'ready':True})
    # Lease boot requires two claims only on first iteration.
    if self.remote.records[plan['task_id']]['state']=='queued':self.request('/remote/claim',{'ready':True})
    commands=[];barrier='';number=0;deadline=time.monotonic()+8
    while time.monotonic()<deadline:
     code,event=self.request('/dialogue/poll');self.assertEqual(code,200);op=event['op']
     if op=='done':break
     if op!='wait':
      commands.append(op)
      if op=='hid_home':self.stage=0;output='HID_HOME_REPORT_SENT'
      elif op=='hid_pointer':self.stage+=1;output='HID_POINTER_REPORT_SENT'
      elif op=='type_text':self.stage=3;output='__PC_EXIT_0__'
      else:raise AssertionError(op)
      self.assertEqual(self.request('/dialogue/result',dict(id=event['id'],ok=True,output=output))[0],200)
     number+=1
     code,img=self.request('/app-screen/frame',frame(self.stage),'screen',{'Content-Type':'image/jpeg','X-Screen-Sequence':str(number),'X-Screen-Barrier':barrier})
     self.assertIn(code,(200,202));barrier=img.get('barrier',barrier);time.sleep(.015)
    else:raise AssertionError('timeout')
    result=self.command('status',task_id=plan['task_id'])[1];self.assertEqual((result['state'],result['verified']),('done',True))
    self.assertEqual(commands,['hid_home','hid_pointer','hid_pointer','type_text']);self.assertTrue(calls[-1])
    self.assertEqual(calls,[False,False,False,False,True])
    self.assertEqual(self.command('save',task_id=plan['task_id'])[0],200)
    code,cards=self.command('skills');self.assertEqual(code,200);card=cards['skills'][-1]
    self.assertEqual(set(card),{'id','name','group','description','requirements','parameters'})
    self.assertNotIn('steps',card)
    code,replay=self.command('skill',skill_id=card['id'],parameters={})
    self.assertEqual((code,replay['state']),(200,'pending'))
    self.assertEqual(self.command('skill',skill_id='f'*24,parameters={})[0],409)
    self.command('stop');self.mailbox.jobs.clear();self.mailbox.high.clear();app_screen.SEQUENCES.clear()
 def test_device_authority_preview_and_idempotency(self):
  ident=uuid.uuid4().hex
  code,plan=self.command('prepare',request_id=ident,text='打开微信找到测试联系人')
  self.assertEqual(code,200);self.assertEqual(plan['state'],'pending');self.assertFalse(self.mailbox.jobs)
  self.assertEqual(self.command('prepare',request_id=ident,text='打开微信找到测试联系人'),(code,plan))
  self.assertEqual(len(self.remote.records),1)
  self.assertEqual(self.command('prepare',request_id=ident,text='打开微信找到王明')[0],409)
  self.assertEqual(self.command('prepare',text='打开微信找到测试联系人',owner=['forged'])[0],409)
  self.assertEqual(self.request('/board-control',dict(session='a'*32,request_id=uuid.uuid4().hex,operation='status'),extra={'Authorization':'Bearer invalid'})[0],403)
 def test_stop_and_retired_sessions_reject_late_confirm(self):
  _,plan=self.command('prepare',text='打开微信找到测试联系人')
  confirm_id=uuid.uuid4().hex
  self.assertEqual(self.command('confirm',request_id=confirm_id,task_id=plan['task_id'])[1]['state'],'queued')
  self.assertEqual(self.command('stop')[0],200)
  self.assertEqual(self.command('confirm',request_id=confirm_id,task_id=plan['task_id'])[1]['state'],'stopped')
  self.assertEqual(self.command('confirm',task_id=plan['task_id'])[0],409)
  _,new=self.command('prepare',session='b'*32,text='打开微信找到测试联系人')
  self.assertEqual(self.command('confirm',task_id=plan['task_id'])[0],403)
  self.assertEqual(self.command('disconnect',session='b'*32)[0],200)
  self.assertEqual(self.command('confirm',session='b'*32,task_id=new['task_id'])[0],403)
 def test_unseen_old_disconnect_does_not_replace_current(self):
  _,plan=self.command('prepare',session='b'*32,text='打开微信找到测试联系人')
  self.assertEqual(self.command('confirm',session='b'*32,task_id=plan['task_id'])[1]['state'],'queued')
  self.assertEqual(self.command('disconnect',session='a'*32)[0],200)
  self.assertEqual(self.command('status',session='b'*32,task_id=plan['task_id'])[1]['state'],'queued')
  self.assertEqual(self.command('prepare',session='a'*32,text='打开微信找到测试联系人')[0],403)
  self.assertEqual(self.remote.records[plan['task_id']]['state'],'queued')
 def test_generic_prepare_and_explicit_forbidden_actions(self):
  for text in ('打开设置','打开浏览器搜索天气','打开地图搜索北京'):
   self.assertEqual(self.command('prepare',text=text)[0],200)
  for text in ('adb shell input tap 1 2','打开微信发送消息给测试联系人','打开支付宝支付十元','打开相册删除照片'):
   self.assertEqual(self.command('prepare',text=text)[0],409)
if __name__=='__main__':unittest.main()
