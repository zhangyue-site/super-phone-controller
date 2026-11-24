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
  super().setUp();self.control_auth=Authority(firmware_scope=False)
  self.ap=patch.object(app_control,'AUTHORITY',self.control_auth);self.ap.start()
  self.frames=patch.object(app_screen,'SEQUENCES',{});self.frames.start()
  self.remote.binding_allowed=remote_http.binding_allowed
 def tearDown(self):
  self.frames.stop();self.ap.stop();super().tearDown()
 def grant(self):
  code,c=self.request('/app-control/challenge',{'device':'epaper-01'});self.assertEqual(code,200)
  proof=hmac.new(b'synthetic-device-only',b'PCFLASH1\nepaper-01\n'+bytes.fromhex(c['challenge']),hashlib.sha256).hexdigest()
  with patch('display_service.firmware.release',side_effect=FileNotFoundError('No firmware is published for this control-only device')):
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
  self.assertEqual((code,result['state']),(200,'stopping'))
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
  with patch('display_service.firmware.release',side_effect=FileNotFoundError('No firmware is published for this control-only device')):
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

 def test_stable_code_rotate_and_public_summary_contract(self):
  parent=self.grant();headers={'Authorization':'Bearer '+parent}
  _,first=self.request('/app-control/pair-issue',{'format':'pin4'},extra=headers)
  _,again=self.request('/app-control/pair-issue',{'format':'pin4'},extra=headers)
  self.assertEqual(first['code'],again['code']);self.assertTrue(first['persistent'])
  controller=self.paired(parent)
  _,plan=self.command(controller,'prepare',text='打开微信找到李洋')
  self.assertEqual(plan['cloudTask']['taskId'],plan['task_id'])
  self.assertEqual(plan['cloudTask']['source'],'android-app')
  self.assertFalse(plan['cloudTask']['verified'])
  self.assertNotIn('owner',plan['cloudTask']);self.assertIn('observedAt',plan)
  code,rotated=self.request('/app-control/pair-rotate',{},extra=headers)
  self.assertEqual(code,200);self.assertNotEqual(first['code'],rotated['code'])
  self.assertEqual(self.command(controller,'status')[0],403)

 def test_screen_status_has_real_remote_task_and_safe_ai_summary(self):
  parent=self.grant();_,plan=self.command(parent,'prepare',text='打开微信找到李洋')
  code,data=self.request('/app-screen/status',kind='screen')
  self.assertEqual(code,200);self.assertEqual(data['cloudTask']['taskId'],plan['task_id'])
  self.assertEqual(data['cloudTask']['source'],'android-app');self.assertIsNotNone(data['cloudTask']['updatedAt'])
  self.assertIn('observedAt',data);self.assertFalse(data['verified'])
  self.remote.records.clear()
  j=self.mailbox.create('epaper-01','a'*16,1);j.agent_job=True;j.reply='PRIVATE INTERNAL REASONING secret'
  code,data=self.request('/app-screen/status',kind='screen')
  self.assertEqual(code,200);self.assertEqual(data['cloudTask']['source'],'cloud-ai')
  self.assertIsNone(data['cloudTask']['updatedAt']);self.assertFalse(data['cloudTask']['verified'])
  self.assertNotIn('PRIVATE',json.dumps(data))

 def test_legacy_issue_contract_and_revocation_is_unconfirmed(self):
  parent=self.grant();headers={'Authorization':'Bearer '+parent}
  code,legacy=self.request('/app-control/pair-issue',{},extra=headers)
  self.assertEqual(code,200);self.assertRegex(legacy['code'],r'^[A-Za-z0-9_-]{43}$')
  self.assertEqual(legacy['expiresIn'],120)
  _,grant=self.request('/app-control/pair-redeem',{'code':legacy['code']})
  code,result=self.request('/app-control/pair-revoke',{},extra=headers)
  self.assertEqual(result['state'],'stopping');self.assertFalse(result['verified'])
  self.assertEqual(self.command(grant['ticket'],'status')[0],403)

 def test_persistent_restore_http_requires_online_parent_and_revokes(self):
  parent=self.grant();headers={'Authorization':'Bearer '+parent}
  _,pin=self.request('/app-control/pair-issue',{'format':'pin4'},extra=headers)
  _,grant=self.request('/app-control/pair-redeem',{'code':pin['code']})
  binding=grant['bindingToken']
  code,restored=self.request('/app-control/pair-restore',{'bindingToken':binding})
  self.assertEqual(code,200);self.assertEqual(restored['bindingToken'],binding)
  self.assertEqual(restored['scope'],'phone-commands')
  self.request('/app-control/pair-revoke',{},extra=headers)
  self.assertEqual(self.request('/app-control/pair-restore',{'bindingToken':binding})[0],403)

 def test_new_target_authorization_restores_binding_without_reissuing_code(self):
  parent=self.grant();headers={'Authorization':'Bearer '+parent}
  _,pin=self.request('/app-control/pair-issue',{'format':'pin4'},extra=headers)
  _,grant=self.request('/app-control/pair-redeem',{'code':pin['code']})
  new_parent=self.grant()
  self.assertNotEqual(parent,new_parent)
  self.assertEqual(self.command(grant['ticket'],'status')[0],403)
  code,restored=self.request('/app-control/pair-restore',{'bindingToken':grant['bindingToken']})
  self.assertEqual(code,200);self.assertEqual(restored['bindingToken'],grant['bindingToken'])
  self.assertEqual(self.command(restored['ticket'],'status')[0],200)

 def maintenance_store(self):
  # Each scenario uses an isolated, real SQLite pairing DB and the HTTP harness.
  pairings=app_control.Pairings(lambda ticket:app_control.owner(ticket)[3],path=self.root/'pairings.sqlite3')
  self.addCleanup(pairings.db.close)
  context=patch.object(app_control,'PAIRINGS',pairings);context.start();self.addCleanup(context.stop)
  return pairings

 def maintenance(self,ticket,path,body=None):
  return self.request('/app-control/maintenance-'+path,body,extra={'Authorization':'Bearer '+ticket})

 def test_maintenance_target_reports_latest_only_controller_reads_no_actions(self):
  from display_service import app_maintenance
  pairings=self.maintenance_store();parent=self.grant();controller=self.paired(parent)
  self.assertEqual(self.maintenance(controller,'read'),(200,{'appMaintenance':None}))
  self.assertIsNone(pairings.db.execute("SELECT 1 FROM sqlite_master WHERE name='app_maintenance'").fetchone())
  report={'installedCode':97,'installedName':'1.4.17','state':'downloading','targetCode':98}
  with patch.object(app_maintenance,'now_seconds',return_value=1700000000):
   self.assertEqual(self.maintenance(parent,'report',report),(200,{'accepted':True}))
  with patch.object(app_maintenance,'now_seconds',return_value=1700000042):
   wanted=dict(report,receivedAt='2023-11-14T22:13:20Z',ageSeconds=42)
   self.assertEqual(self.maintenance(controller,'read',{}),(200,{'appMaintenance':wanted}))
   self.assertEqual(self.maintenance(parent,'read'),(200,{'appMaintenance':wanted}))
  newer={'installedCode':98,'installedName':'1.4.18','state':'current'}
  self.assertEqual(self.maintenance(parent,'report',newer)[0],200)
  latest=self.maintenance(controller,'read')[1]['appMaintenance']
  self.assertEqual({k:latest[k] for k in newer},newer);self.assertNotIn('targetCode',latest)
  self.assertEqual(pairings.db.execute('SELECT count(*) FROM app_maintenance').fetchone()[0],1)
  self.assertFalse(self.mailbox.jobs);self.assertFalse(self.remote.records)
  self.assertEqual(self.command(controller,'status')[1]['state'],'idle')

 def test_maintenance_identity_and_expiration(self):
  pairings=self.maintenance_store();parent=self.grant();controller=self.paired(parent)
  second='m'*43;self.control_auth.tickets[second]=(self.control_auth.clock()+300,'other-target','f'*64)
  second_controller=self.paired(second)
  report={'installedCode':97,'installedName':'1.4.17','state':'ready'}
  self.assertEqual(self.maintenance(controller,'report',report)[0],403)
  self.assertEqual(self.maintenance(parent,'report',report)[0],200)
  self.assertEqual(self.maintenance(second_controller,'read'),(200,{'appMaintenance':None}))
  self.assertEqual(self.maintenance(second,'report',dict(report,installedCode=98,installedName='1.4.18'))[0],200)
  self.assertEqual(self.maintenance(controller,'read')[1]['appMaintenance']['installedCode'],97)
  self.assertEqual(self.maintenance(second_controller,'read')[1]['appMaintenance']['installedCode'],98)
  self.assertEqual(self.maintenance(self.ticket,'read')[0],403)  # screen credential
  self.assertEqual(self.request('/app-control/maintenance-read')[0],403)  # board bearer
  self.assertEqual(self.maintenance('invalid','read')[0],403)
  pairings.tickets[controller]=(0,*pairings.tickets[controller][1:])
  self.assertEqual(self.maintenance(controller,'read')[0],403)
  fresh_controller=self.paired(parent);new_parent=self.grant()
  self.assertEqual(self.maintenance(parent,'report',report)[0],403)
  self.assertEqual(self.maintenance(fresh_controller,'read')[0],403)
  self.control_auth.tickets[new_parent]=(0,'epaper-01','f'*64)
  self.assertEqual(self.maintenance(new_parent,'report',report)[0],403)
  self.assertEqual(self.maintenance(second_controller,'read')[0],200)

 def test_maintenance_schema_and_privacy(self):
  from display_service import app_maintenance
  pairings=self.maintenance_store();parent=self.grant()
  base={'installedCode':97,'installedName':'1.4.17','state':'idle'}
  for state in ('idle','checking','current','available','downloading','verifying','ready','permission_required','installer_opened','error'):
   with self.subTest(state=state):
    self.assertEqual(self.maintenance(parent,'report',dict(base,state=state))[0],200)
  changes=[{'installedCode':True},{'installedCode':0},{'installedCode':3.0},{'targetCode':None},
           {'targetCode':False},{'targetCode':2147483648},{'installedName':'1.4.17\n'},
           {'installedName':'10.0.0.1'},{'installedName':'001234'},{'installedName':'私有消息'},
           {'state':'unspecified'},{'state':['idle']},{'device':'other-target'},
           {'ip':'10.0.0.1'},{'port':10000},{'pairingCode':'001234'},
           {'message':'unsent note'},{'receivedAt':'2000-01-01T00:00:00Z'},{'ageSeconds':0}]
  for change in changes:
   with self.subTest(change=change):self.assertEqual(self.maintenance(parent,'report',dict(base,**change))[0],400)
  for key in base:
   with self.subTest(missing=key):
    self.assertEqual(self.maintenance(parent,'report',{k:v for k,v in base.items() if k!=key})[0],400)
  duplicate=b'{"installedCode":97,"installedName":"1.4.17","state":"private text","state":"idle"}'
  self.assertEqual(self.maintenance(parent,'report',duplicate)[0],400)
  import http.client
  conn=http.client.HTTPConnection('127.0.0.1',self.server.server_address[1],timeout=5)
  try:
   conn.request('GET','/app-control/maintenance-read',headers={'Authorization':'Bearer '+parent})
   response=conn.getresponse();self.assertEqual(response.status,405)
   self.assertEqual(response.getheader('Cache-Control'),'no-store');self.assertEqual(json.loads(response.read()),{})
  finally:conn.close()
  for route in ('read','report'):
   self.assertEqual(self.maintenance(parent,route,{'noise':'x'*700})[0],400)
  self.assertEqual(self.maintenance(parent,'read',{'device':'other-target'})[0],400)
  with patch.dict('os.environ',{'EPAPER_REMOTE_CONTROL':'0'}):
   self.assertEqual(self.maintenance(parent,'read')[0],503)
  self.assertEqual(pairings.db.execute('SELECT state FROM app_maintenance').fetchall(),[('error',)])
  # Reopen the old pairing database independently, without converting or revoking its existing data.
  other=app_control.Pairings(lambda _:None,path=self.root/'pairings.sqlite3')
  try:self.assertEqual(app_maintenance.read(other.db,'epaper-01',0)['ageSeconds'],0)
  finally:other.db.close()
