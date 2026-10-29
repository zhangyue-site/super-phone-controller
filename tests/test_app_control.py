import hashlib,hmac,json,unittest,time
from test_wechat_nav import frame
from unittest.mock import patch
import test_remote_http as http_tests
from display_service import app_control,remote_http,app_screen
from display_service.app_ota import Authority

class AppControlTests(http_tests.RemoteHttpTests):
 # Keep only App cases; parent supplies the real HTTP server/board harness.
 test_both_origins_real_http_flow_and_scoped_verified_result=None
 test_bridge_auth_unknown_peer_cross_confirmation_and_stop=None
 test_remote_stop_blocks_voice_asr_already_in_flight=None
 def setUp(self):
  super().setUp();self.control_auth=Authority()
  self.ap=patch.object(app_control,'AUTHORITY',self.control_auth);self.ap.start()
  self.frames=patch.object(app_screen,'SEQUENCES',{});self.frames.start()
  self.remote.binding_allowed=remote_http.binding_allowed
 def tearDown(self):
  self.frames.stop();self.ap.stop();super().tearDown()
 def grant(self):
  code,c=self.request('/app-control/challenge',{'device':'epaper-01'});self.assertEqual(code,200)
  proof=hmac.new(b'synthetic-device-only',b'PCFLASH1\nepaper-01\n'+bytes.fromhex(c['challenge']),hashlib.sha256).hexdigest()
  with patch('display_service.firmware.release',return_value=({'sha256':'f'*64,'version':'test','size':100},b'')):
   code,g=self.request('/app-control/authorize',{'device':'epaper-01','challenge':c['challenge'],'proof':proof})
  self.assertEqual(code,200);self.assertEqual(g['scope'],'phone-commands');return g['ticket']
 def command(self,ticket,operation,**kw):
  return self.request('/app-control/command',dict(operation=operation,**kw),extra={'Authorization':'Bearer '+ticket})
 def test_preview_confirm_claim_stop_and_private_result(self):
  ticket=self.grant()
  code,plan=self.command(ticket,'prepare',text='打开微信找到李洋');self.assertEqual(code,200);self.assertEqual(plan['state'],'pending');self.assertFalse(self.mailbox.jobs)
  self.assertEqual(plan['reply'].count('请在两分钟内点击'),1)
  self.assertNotIn('/phone',self.command(ticket,'status')[1]['reply'])
  self.assertEqual(self.bridge('confirm',task_id=plan['task_id'])[0],409)
  self.assertEqual(self.command(ticket,'confirm',task_id=plan['task_id'])[1]['state'],'queued')
  self.request('/remote/claim',{'ready':True});self.assertEqual(self.request('/remote/claim',{'ready':True})[1]['op'],'start')
  self.assertEqual(self.command(ticket,'stop')[0],200)
  self.assertEqual(self.request('/remote/status')[1]['op'],'cancelled')
  self.assertEqual(self.command(ticket,'status')[1]['state'],'stopped')
 def test_app_command_verified_visual_hid_result(self):
  ticket=self.grant();_,plan=self.command(ticket,'prepare',text='打开微信找到李洋')
  self.command(ticket,'confirm',task_id=plan['task_id']);self.request('/remote/claim',{'ready':True})
  self.assertEqual(self.request('/remote/claim',{'ready':True})[1]['op'],'start')
  commands=[];barrier='';number=0;deadline=time.monotonic()+8
  while time.monotonic()<deadline:
   code,event=self.request('/dialogue/poll');self.assertEqual(code,200)
   op=event['op']
   if op=='done':break
   if op!='wait':
    commands.append(op)
    if op=='hid_home':self.stage=0;output='HID_HOME_REPORT_SENT'
    elif op=='hid_pointer':self.stage+=1;output='HID_POINTER_REPORT_SENT'
    elif op=='hid_text':self.stage=3;output='HID_TEXT_REPORT_SENT'
    else:raise AssertionError(op)
    self.assertEqual(self.request('/dialogue/result',{'id':event['id'],'ok':True,'output':output})[0],200)
   number+=1
   code,img=self.request('/app-screen/frame',frame(min(self.stage,3)),'screen',{'Content-Type':'image/jpeg','X-Screen-Sequence':str(number),'X-Screen-Barrier':barrier})
   self.assertIn(code,(200,202));barrier=img.get('barrier',barrier);time.sleep(.015)
  else:raise AssertionError('timeout')
  code,result=self.command(ticket,'status');self.assertEqual((code,result['state'],result['verified']),(200,'done',True))
  self.assertEqual(commands,['hid_home','hid_pointer','hid_pointer','hid_text','hid_pointer'])
  self.assertEqual(self.command(ticket,'save',task_id=plan['task_id'])[0],200)
 def test_scope_expiry_supersession_and_revocation(self):
  ticket=self.grant();_,plan=self.command(ticket,'prepare',text='打开微信找到李洋')
  self.assertEqual(self.command(self.ticket,'confirm',task_id=plan['task_id'])[0],403)
  newer=self.grant()
  self.assertEqual(self.command(ticket,'confirm',task_id=plan['task_id'])[0],403)
  self.assertEqual(self.command(newer,'confirm',task_id=plan['task_id'])[0],409)
  self.assertEqual(self.command(newer,'status')[1]['state'],'idle')
  self.assertEqual(self.remote.records[plan['task_id']]['state'],'error')
  self.control_auth.tickets[newer]=(0,'epaper-01','f'*64)
  self.assertEqual(self.command(newer,'status')[0],403)
 def test_pairing_does_not_replace_relay_and_is_command_only(self):
  relay=self.grant()
  hdr={"Authorization":"Bearer "+relay}
  code, issued=self.request("/app-control/pair-issue",{},extra=hdr)
  self.assertEqual(code,200)
  code, paired=self.request("/app-control/pair-redeem",{"code":issued["code"]})
  self.assertEqual(code,200)
  controller=paired["ticket"]
  self.assertEqual(self.command(relay,"status")[0],200)
  self.assertEqual(self.command(controller,"status")[0],200)
  self.assertNotEqual(self.request("/app-relay/poll",{"nonce":"0"*32},extra={"Authorization":"Bearer "+controller})[0],200)
  self.assertNotEqual(self.request("/app-control/pair-redeem",{"code":issued["code"]})[0],200)
  self.assertNotEqual(self.request("/app-control/pair-issue",{},extra={"Authorization":"Bearer "+controller})[0],200)
 def paired(self, parent):
  code, issued=self.request('/app-control/pair-issue',{},extra={'Authorization':'Bearer '+parent});self.assertEqual(code,200)
  code, grant=self.request('/app-control/pair-redeem',{'code':issued['code']});self.assertEqual(code,200)
  return grant['ticket']
 def test_paired_task_runs_and_target_revoke_cancels_it(self):
  parent=self.grant();controller=self.paired(parent)
  code,plan=self.command(controller,'prepare',text='打开微信找到李洋');self.assertEqual(code,200)
  code,result=self.command(controller,'confirm',task_id=plan['task_id']);self.assertEqual((code,result['state']),(200,'queued'))
  self.request('/remote/claim',{'ready':True})
  self.assertEqual(self.request('/remote/claim',{'ready':True})[1]['op'],'start')
  self.assertEqual(self.command(controller,'status')[1]['state'],'running')
  code,result=self.request('/app-control/pair-revoke',{},extra={'Authorization':'Bearer '+parent})
  self.assertEqual((code,result['state']),(200,'stopped'))
  self.assertEqual(self.command(controller,'status')[0],403)
  self.assertEqual(self.request('/remote/status')[1]['op'],'cancelled')
  self.assertIn(self.remote.records[plan['task_id']]['state'],('stopped','error'))
  self.assertEqual(self.command(parent,'status')[0],200)
 def test_parent_renew_preserves_paired_identity_and_supersession_invalidates(self):
  parent=self.grant();controller=self.paired(parent)
  identity=app_control.controller_owner(controller)
  old_expiry=self.control_auth.tickets[parent][0]
  code,c=self.request('/app-control/challenge',{'device':'epaper-01'});self.assertEqual(code,200)
  proof=hmac.new(b'synthetic-device-only',b'PCFLASH1\nepaper-01\n'+bytes.fromhex(c['challenge']),hashlib.sha256).hexdigest()
  with patch('display_service.firmware.release',return_value=({'sha256':'f'*64,'version':'test','size':100},b'')):
   code,result=self.request('/app-control/renew',{'device':'epaper-01','challenge':c['challenge'],'proof':proof},extra={'Authorization':'Bearer '+parent})
  self.assertEqual(code,200);self.assertGreaterEqual(self.control_auth.tickets[parent][0],old_expiry)
  self.assertEqual(app_control.controller_owner(controller),identity)
  self.assertEqual(set(self.control_auth.tickets),{parent})
  self.assertEqual(self.request('/app-control/pair-renew',{},extra={'Authorization':'Bearer '+controller})[0],200)
  _,plan=self.command(controller,'prepare',text='打开微信找到李洋')
  self.grant()
  self.assertEqual(self.command(controller,'confirm',task_id=plan['task_id'])[0],403)
  self.assertEqual(self.command(parent,'status')[0],403)
 def test_pair_capability_cannot_relay_ota_renew_target_or_revoke(self):
  parent=self.grant();controller=self.paired(parent);hdr={'Authorization':'Bearer '+controller}
  with patch.dict('os.environ',{'EPAPER_RELAY_CONTROL':'1'}):
   self.assertEqual(self.request('/app-relay/poll',{'nonce':'0'*32},extra=hdr)[0],403)
  conn=http_tests.http.client.HTTPConnection(*self.server.server_address,timeout=4)
  conn.request('GET','/app-ota/image',headers=hdr);response=conn.getresponse()
  self.assertEqual(response.status,403);response.read();conn.close()
  self.assertEqual(self.request('/app-control/renew',{'device':'epaper-01','challenge':'0'*64,'proof':'0'*64},extra=hdr)[0],403)
  self.assertEqual(self.request('/app-control/pair-revoke',{},extra=hdr)[0],403)
  self.assertEqual(self.request('/app-control/pair-issue',{},extra=hdr)[0],403)
 def test_no_injected_shell_or_owner(self):
  ticket=self.grant()
  self.assertEqual(self.command(ticket,'prepare',text='adb shell input tap 1 2')[0],409)
  self.assertEqual(self.command(ticket,'confirm')[0],409)
  self.assertEqual(self.command(ticket,'prepare',text='打开微信找到李洋',device='other')[0],409)
  self.assertEqual(self.request('/app-control/authorize',{'device':'epaper-01','challenge':'0'*64,'proof':'0'*64})[0],409)
if __name__=='__main__':unittest.main()
