import http.client,json
import test_remote_http as fixture
class VoiceUIHttpTests(fixture.RemoteHttpTests):
 test_both_origins_real_http_flow_and_scoped_verified_result=None
 test_bridge_auth_unknown_peer_cross_confirmation_and_stop=None
 test_remote_stop_blocks_voice_asr_already_in_flight=None
 def setUp(self):
  super().setUp();self.j=self.mailbox.create('epaper-01','a'*16,1);self.j.ui_protocol='plan-v1';self.j.ui_revision=2;self.j.ui_heard='打开设置';self.j.ui_plan=['先回手机桌面','按画面寻找并打开','核对最终画面'];self.j.state='plan'
 def raw(self,path,body,sequence=1,token='synthetic-device-only'):
  headers={'Authorization':'Bearer '+token,'X-Voice-Session':'a'*16,'X-Voice-Sequence':str(sequence),'Content-Type':'application/json'}
  c=http.client.HTTPConnection(*self.server.server_address,timeout=3);c.request('POST',path,json.dumps(body),headers);r=c.getresponse();result=(r.status,r.read());c.close();return result
 def test_screen_revision_is_consistent_and_never_acks_by_fetching(self):
  code,data=self.raw('/dialogue/screen',{'revision':2});self.assertEqual((code,len(data)),(200,5000));self.assertEqual(self.j.ui_seen_revision,0)
  self.assertEqual(self.raw('/dialogue/screen',{'revision':1})[0],409)
 def test_seen_requires_exact_turn_revision_and_auth(self):
  self.assertEqual(self.raw('/dialogue/seen',{'revision':1})[0],409);self.assertEqual(self.raw('/dialogue/seen',{'revision':True})[0],409)
  self.assertEqual(self.raw('/dialogue/seen',{'revision':2},sequence=2)[0],409);self.assertEqual(self.raw('/dialogue/seen',{'revision':2},token='invalid')[0],401)
  self.assertEqual(self.j.ui_seen_revision,0);self.assertEqual(self.raw('/dialogue/seen',{'revision':2})[0],200);self.assertEqual(self.j.ui_seen_revision,2)
 def test_legacy_client_never_uses_screen_receipt_protocol(self):
  self.j.ui_protocol='';self.assertEqual(self.raw('/dialogue/seen',{'revision':2})[0],409)
