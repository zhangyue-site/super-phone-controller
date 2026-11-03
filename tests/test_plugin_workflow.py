import json,tempfile,unittest
from pathlib import Path
from display_service.plugin_workflow import PluginSessions,render_entry
from test_remote_control import FakeConversation
from display_service.remote_control import RemoteControl
class PluginTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.path=Path(self.tmp.name)/"private.json";self.path.write_text(json.dumps({"synthetic.search":{"text":"打开设置搜索{query}","parameters":{"query":{"type":"text","maxLength":16}}}}))
  self.now=[100.];self.c=FakeConversation();self.r=RemoteControl(self.c,Path(self.tmp.name)/"tasks.json",clock=lambda:self.now[0],screen_ready=lambda _:True)
  self.s=PluginSessions(clock=lambda:self.now[0]);self.r.binding_allowed=self.s.allowed
  self.base=dict(boot="a"*32,session="b"*32,request_id="c"*32,operation="prepare",entry="synthetic.search",parameters={"query":"电池"})
 def call(self,**values):return self.s.dispatch("board",dict(self.base,**values),self.r,self.path)
 def test_default_closed_unknown_and_parameter_schema(self):
  with self.assertRaises(ValueError):render_entry(None,"synthetic.search",{})
  for entry,params in [("../script",{}),("unknown",{}),("synthetic.search",{"query":"x","extra":"x"}),("synthetic.search",{"query":"x"*17}),("synthetic.search",{"query":True})]:
   with self.subTest(entry=entry,params=params),self.assertRaises(ValueError):render_entry(self.path,entry,params)
 def test_prepare_confirm_claim_and_real_status(self):
  plan=self.call();self.assertEqual(plan["state"],"pending");self.assertFalse(self.c.started)
  confirm=dict(operation="confirm",task_id=plan["task_id"],confirmation=plan["confirmation"],request_id="d"*32)
  self.base={k:v for k,v in self.base.items() if k not in ("entry","parameters")}
  queued=self.call(**confirm);self.assertEqual(queued["state"],"queued")
  lease=self.r.claim("board","e"*16,1,True,"absolute-v1")["lease"]
  self.assertEqual(self.r.claim("board","e"*16,2,True,"absolute-v1",lease)["op"],"start")
  self.assertEqual(self.c.started,["打开设置搜索电池"])
  self.assertEqual(self.call(operation="status",task_id=plan["task_id"],request_id="f"*32)["state"],"running")
  stop=self.call(operation="stop",request_id="0"*32);self.assertEqual(stop["state"],"stopped")
  self.assertTrue(self.c.mailbox.jobs["board"].cancelled)
 def test_confirm_requires_exact_session_nonce_and_unexpired_gesture(self):
  plan=self.call();self.base={k:v for k,v in self.base.items() if k not in ("entry","parameters")}
  args=dict(operation="confirm",task_id=plan["task_id"],confirmation=plan["confirmation"],request_id="d"*32)
  with self.assertRaises(PermissionError):self.call(**dict(args,session="e"*32))
  with self.assertRaises(PermissionError):self.call(**dict(args,confirmation="e"*32))
  self.now[0]+=121
  with self.assertRaises(PermissionError):self.call(**args)
 def test_replays_stop_and_replaced_session_do_not_requeue(self):
  plan=self.call()
  with self.assertRaises(PermissionError):self.call()
  self.base={k:v for k,v in self.base.items() if k not in ("entry","parameters")}
  self.call(operation="stop",request_id="d"*32)
  with self.assertRaises(PermissionError):self.call(operation="confirm",task_id=plan["task_id"],confirmation=plan["confirmation"],request_id="e"*32)
 def test_registry_changes_revoke_pending_confirmation(self):
  plan=self.call();self.base={k:v for k,v in self.base.items() if k not in ("entry","parameters")}
  self.path.write_text("{}")
  with self.assertRaises((PermissionError,ValueError)):self.call(operation="confirm",task_id=plan["task_id"],confirmation=plan["confirmation"],request_id="d"*32)
 def test_unknown_fields_and_cross_device_task_rejected(self):
  with self.assertRaises(ValueError):self.call(command="rm")
  plan=self.call()
  obj=dict(boot="a"*32,session="b"*32,request_id="d"*32,operation="confirm",task_id=plan["task_id"],confirmation=plan["confirmation"])
  with self.assertRaises(PermissionError):self.s.dispatch("other",obj,self.r,self.path)


 def test_stopping_pending_plugin_never_stops_another_origin(self):
  self.call()
  owner=('telegram','other','other','board')
  self.r.binding_allowed=lambda identity:identity[0]=='telegram' or self.s.allowed(identity)
  ident=self.r.prepare(owner,'打开设置')['task_id'];self.r.confirm(owner,ident)
  self.base={k:v for k,v in self.base.items() if k not in ('entry','parameters')}
  self.call(operation='stop',request_id='d'*32)
  self.assertEqual(self.r.records[ident]['state'],'queued')

 def test_stop_remains_available_at_request_capacity(self):
  self.call();self.base={k:v for k,v in self.base.items() if k not in ('entry','parameters')}
  self.s.devices['board']['requests']={f'{i:032x}' for i in range(512)}
  self.assertEqual(self.call(operation='stop',request_id='f'*32)['state'],'stopped')

 def test_stopped_session_does_not_accumulate_flooded_stop_ids(self):
  self.call();self.base={k:v for k,v in self.base.items() if k not in ('entry','parameters')}
  self.call(operation='stop',request_id='d'*32)
  before=len(self.s.devices['board']['requests'])
  for i in range(10):
   with self.assertRaises(PermissionError):self.call(operation='stop',request_id=f'{i:032x}')
  self.assertEqual(len(self.s.devices['board']['requests']),before)
