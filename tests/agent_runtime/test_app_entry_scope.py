import unittest
from display_service import agent_runtime as r
from display_service.agent_gates import GateError
class AppScope(unittest.TestCase):
 def test_folder_cannot_substitute_for_requested_application(self):
  with self.assertRaises(GateError)as cm:r._locate(dict(capability="open_app",target="谷歌",locator="text",bounds=[0,0,20,20]),{},("浏览器",))
  self.assertEqual(cm.exception.code,"visual_app_scope_mismatch");self.assertEqual(cm.exception.recovery,"observe_image")
 def test_unrelated_video_application_cannot_substitute(self):
  with self.assertRaises(GateError)as cm:r._locate(dict(capability="open_app",target="腾讯视频",locator="text",bounds=[0,0,20,20]),{},("优酷视频",))
  self.assertEqual(cm.exception.code,"visual_app_scope_mismatch")

class ScopeRetry(unittest.TestCase):
 def test_third_mismatched_app_plan_stops_without_input_retry(self):
  from display_service.agent_doctor import require_observation_recovery
  for repeat in (1,2):require_observation_recovery(dict(code="visual_app_scope_mismatch",repeat=repeat,recovery="refresh_visual"))
  with self.assertRaises(GateError)as cm:require_observation_recovery(dict(code="visual_app_scope_mismatch",repeat=3,recovery="refresh_visual"))
  self.assertEqual(cm.exception.code,"planner_scope_blocked");self.assertEqual(cm.exception.recovery,"stop")
