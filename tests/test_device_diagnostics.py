import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from display_service import events,control
from test_remote_control import FakeConversation
from display_service.remote_control import RemoteControl

class DiagnosticTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.now=100.
  self.c=FakeConversation();self.r=RemoteControl(self.c,self.root/"state.json",clock=lambda:self.now,screen_ready=lambda _:True)
  self.owner=("android-app","owner","owner","board")
  self.root_patch=patch.object(control,"ROOT",self.root);self.root_patch.start()
 def tearDown(self):self.root_patch.stop();self.tmp.cleanup()
 def rows(self,*rows):
  folder=self.root/"events";folder.mkdir(exist_ok=True)
  (folder/"board.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows))
 def event(self,**kw):return dict(dict(boot=1,seq=1,event="exec",a=0,receivedAt=100),**kw)
 def test_exec_expires_and_future_is_unknown(self):
  self.rows(self.event())
  with patch.object(events.time,"time",return_value=110):self.assertEqual(events.latest_exec("board"),0)
  with patch.object(events.time,"time",return_value=146):self.assertIsNone(events.latest_exec("board"))
  with patch.object(events.time,"time",return_value=99):self.assertIsNone(events.latest_exec("board"))
 def test_new_boot_and_invalid_code_do_not_reuse_old_ready(self):
  self.rows(self.event(),self.event(boot=2,seq=1,event="boot",receivedAt=101))
  with patch.object(events.time,"time",return_value=102):self.assertIsNone(events.latest_exec("board"))
  self.rows(self.event(a=99))
  with patch.object(events.time,"time",return_value=102):self.assertIsNone(events.latest_exec("board"))
 def test_queued_status_missing_and_stale_heartbeat_is_readable(self):
  ident=self.r.prepare(self.owner,"打开设置")["task_id"];self.r.confirm(self.owner,ident)
  self.assertIn("还没有板端心跳",self.r.status(self.owner,ident)["reply"])
  self.rows(self.event())
  with patch.object(events.time,"time",return_value=146):self.assertIn("心跳已过期",self.r.status(self.owner,ident)["reply"])
 def handshake(self):
  return self.r.claim("board","a"*16,1,False,"absolute-v1")["lease"]
 def test_wait_reasons_preserve_lease_and_sequence_fence(self):
  first=self.r.claim("board","a"*16,1,False,"absolute-v1")
  self.assertEqual(first.get("reason"),"lease_required")
  lease=first["lease"]
  self.assertEqual(self.r.claim("board","a"*16,2,False,"absolute-v1",lease).get("reason"),"device_not_ready")
  self.assertEqual(self.r.claim("board","a"*16,3,True,"old",lease).get("reason"),"pointer_protocol_mismatch")
  self.assertEqual(self.r.claim("board","a"*16,3,True,"absolute-v1",lease).get("reason"),"sequence_rejected")
  ident=self.r.prepare(self.owner,"打开设置")["task_id"];self.r.confirm(self.owner,ident)
  self.r.screen_ready=lambda _:False
  self.assertEqual(self.r.claim("board","a"*16,4,True,"absolute-v1",lease).get("reason"),"screen_not_authorized")
  self.assertFalse(self.c.started)
 def test_diagnostics_is_read_only_and_reports_unknown(self):
  before=dict(self.r.records)
  with patch.object(events.time,"time",return_value=110):out=self.r.diagnostics(self.owner)
  self.assertTrue(out["controlAuthorized"]);self.assertTrue(out["screenAuthorized"])
  self.assertEqual(out["heartbeat"]["state"],"unknown")
  self.assertIsNone(out["pointerCompatible"]);self.assertIsNone(out["frameAgeSeconds"])
  self.assertFalse(out["inputReady"]);self.assertEqual(self.r.records,before)
  self.assertFalse(self.r.path.exists());self.assertFalse(self.c.started)
 def test_diagnostics_fresh_then_expired_claim_and_authorization(self):
  self.rows(self.event());lease=self.handshake()
  self.r.claim("board","a"*16,2,True,"absolute-v1",lease)
  with patch.object(events.time,"time",return_value=110):
   out=self.r.diagnostics(self.owner);self.assertIsNone(out["inputReady"]);self.assertTrue(out["pointerCompatible"])
   self.now+=46;out=self.r.diagnostics(self.owner);self.assertFalse(out["inputReady"]);self.assertIsNone(out["pointerCompatible"])
  self.r.binding_allowed=lambda _:False
  with self.assertRaises(PermissionError):self.r.diagnostics(self.owner)

 def test_frame_requires_payload_and_current_capture_source(self):
  job=self.c.mailbox.create("board","a"*16,1)
  self.c.mailbox.clock=lambda:self.now
  job.video_sequence=1;job.video_received=99;job.video_source="user-consented-app-screen"
  job.video=b"";job.screen_session="capture"
  self.r.screen_source_allowed=lambda device,ticket:ticket=="capture"
  self.assertIsNone(self.r.diagnostics(self.owner)["frameFresh"])
  job.video=b"synthetic";self.assertTrue(self.r.diagnostics(self.owner)["frameFresh"])
  self.now=111;self.assertFalse(self.r.diagnostics(self.owner)["frameFresh"])
  self.r.screen_source_allowed=lambda *_:False
  self.assertIsNone(self.r.diagnostics(self.owner)["frameFresh"])
 def test_voice_busy_is_separate_from_mailbox_busy(self):
  self.r.voice_busy=lambda _:True
  out=self.r.diagnostics(self.owner)
  self.assertTrue(out["voiceBusy"]);self.assertFalse(out["taskBusy"])
  self.assertIn("voice_busy",out["reasons"])

 def test_heartbeat_keeps_last_exec_beyond_ui_event_tail(self):
  self.rows(self.event(),*[self.event(seq=n,event="touch") for n in range(2,105)])
  with patch.object(events.time,"time",return_value=110):
   self.assertEqual(events.latest_exec("board"),0)
 def test_source_grant_must_match_device_and_be_live(self):
  from display_service import remote_http,app_screen
  from display_service.app_ota import Authority
  authority=Authority(clock=lambda:100)
  authority.tickets["capture"]=(101,"board","proof")
  with patch.object(app_screen,"AUTHORITY",authority):
   self.assertTrue(remote_http.screen_source_allowed("board","capture"))
   self.assertFalse(remote_http.screen_source_allowed("other","capture"))
   authority.tickets["capture"]=(100,"board","proof")
   self.assertFalse(remote_http.screen_source_allowed("board","capture"))
