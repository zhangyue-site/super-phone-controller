"""Actual production routing plus read-only legacy BLE session compatibility.

The archived board_control module is not registered by app.Handler. Manual
commands remain exposed through authenticated app_control and the one Gateway.
"""
import unittest,uuid,types
from display_service import board_control
from test_remote_http import RemoteHttpTests
class BoardControlTests(RemoteHttpTests):
 test_both_origins_real_http_flow_and_scoped_verified_result=None
 test_bridge_auth_unknown_peer_cross_confirmation_and_stop=None
 test_remote_stop_blocks_voice_asr_already_in_flight=None
 def test_archived_path_cannot_create_an_alternate_executor(self):
  before=dict(self.remote.records)
  for operation in ('prepare','confirm','skill','stop'):
   code,_=self.request('/board-control',dict(session='a'*32,request_id=uuid.uuid4().hex,operation=operation,text='打开设置'))
   self.assertEqual(code,404)
  self.assertEqual(self.remote.records,before);self.assertFalse(self.mailbox.jobs)
 def test_unknown_device_is_rejected_before_unknown_route(self):
  code,_=self.request('/board-control',{},extra={'Authorization':'Bearer invalid'})
  self.assertEqual(code,401);self.assertFalse(self.mailbox.jobs)
class LegacySessionCompatibility(unittest.TestCase):
 def setUp(self):
  self.s=board_control.Sessions();self.stopped=[];self.cards=[]
  self.remote=types.SimpleNamespace(c=types.SimpleNamespace(skills=types.SimpleNamespace(cards=lambda _:self.cards)),stop_device=lambda d:self.stopped.append(d),stop=lambda owner:{'state':'stopped','terminal':True,'verified':False})
 def call(self,op,session='a'*32,ident=None,**kw):return self.s.dispatch('synthetic',dict(session=session,request_id=ident or uuid.uuid4().hex,operation=op,**kw),self.remote)
 def test_skill_metadata_remains_bounded_and_idempotent(self):
  self.cards[:]=[{'description':'large'*4000}];ident=uuid.uuid4().hex
  first=self.call('skills',ident=ident);self.assertEqual(first['error'],'response_capacity');self.assertEqual(first,self.call('skills',ident=ident))
  with self.assertRaises(ValueError):self.call('stop',ident=ident)
 def test_legacy_disconnect_retires_nonce_without_replacing_current(self):
  self.call('skills',session='b'*32)
  self.call('disconnect',session='a'*32)
  self.assertEqual(self.s.devices['synthetic']['current'],'b'*32)
  with self.assertRaises(PermissionError):self.call('skills',session='a'*32)
  self.call('disconnect',session='b'*32)
  with self.assertRaises(PermissionError):self.call('skills',session='b'*32)
 def test_session_replacement_invalidates_previous_identity(self):
  self.call('skills',session='a'*32);old=self.s.identity('synthetic','a'*32)
  self.call('skills',session='b'*32);self.assertFalse(self.s.allowed(old));self.assertTrue(self.s.allowed(self.s.identity('synthetic','b'*32)));self.assertEqual(self.stopped,['synthetic'])
if __name__=='__main__':unittest.main()
