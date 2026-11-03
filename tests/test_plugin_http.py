import json,unittest
from unittest.mock import patch
from display_service import plugin_workflow
import test_remote_http as support
class PluginHttpTests(unittest.TestCase):
 setUp=support.RemoteHttpTests.setUp
 tearDown=support.RemoteHttpTests.tearDown
 request=support.RemoteHttpTests.request
 def test_real_device_http_empty_registry_and_bound_confirmation(self):
  obj=dict(operation="prepare",boot="a"*32,session="b"*32,request_id="c"*32,entry="synthetic.open",parameters={})
  sessions=plugin_workflow.PluginSessions();self.remote.binding_allowed=sessions.allowed
  registry=self.root/"private-workflows.json";registry.write_text(json.dumps({"synthetic.open":{"text":"打开设置","parameters":{}}}))
  with patch.object(plugin_workflow,"SESSIONS",sessions),patch.dict("os.environ",{"CONTROLLER_PLUGIN_WORKFLOWS":str(registry)}):
   code,plan=self.request("/board-plugin",obj)
   self.assertEqual(code,200);self.assertEqual(plan["state"],"pending");self.assertFalse(self.mailbox.jobs)
   body={k:obj[k] for k in ("boot","session")}
   code,queued=self.request("/board-plugin",dict(body,operation="confirm",request_id="d"*32,task_id=plan["task_id"],confirmation=plan["confirmation"]))
   self.assertEqual((code,queued["state"]),(200,"queued"))
   self.assertEqual(self.request("/board-plugin",dict(body,operation="confirm",request_id="e"*32,task_id=plan["task_id"],confirmation=plan["confirmation"]))[0],403)
   self.assertEqual(self.request("/board-plugin",dict(body,operation="stop",request_id="f"*32))[0],200)
   self.assertFalse(self.mailbox.jobs)
  with patch.object(plugin_workflow,"SESSIONS",plugin_workflow.PluginSessions()),patch.dict("os.environ",{"CONTROLLER_PLUGIN_WORKFLOWS":""}):
   code,reply=self.request("/board-plugin",dict(obj,session="1"*32))
   self.assertEqual(code,409);self.assertIn("未配置",reply["reply"])
 def test_wrong_capture_ticket_cannot_create_plugin(self):
  obj=dict(operation="prepare",boot="a"*32,session="b"*32,request_id="c"*32,entry="synthetic.open",parameters={})
  self.assertEqual(self.request("/board-plugin",obj,kind="screen")[0],403)
