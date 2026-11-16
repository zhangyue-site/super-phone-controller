import importlib,unittest
D=importlib.import_module("display_service.agent_doctor")
class RetryTests(unittest.TestCase):
 def test_third_failed_wait_stops(self):
  for n in (1,2):D.require_observation_recovery(dict(code="target_not_stable",repeat=n,recovery="inspect_pipeline"))
  with self.assertRaises(D.GateError) as c:D.require_observation_recovery(dict(code="target_not_stable",repeat=3,recovery="inspect_pipeline"))
  self.assertEqual(c.exception.code,"observation_pipeline_blocked")
  self.assertEqual(c.exception.recovery,"stop")
 def test_unknown_input_remains_reconciliation(self):
  D.require_observation_recovery(dict(code="target_not_stable",repeat=17,recovery="reconcile_original"))
 def test_other_failures_not_reclassified(self):
  D.require_observation_recovery(dict(code="frame_changed",repeat=17,recovery="refresh_visual"))
 def test_real_doctor_counts_failed_waits(self):
  d=D.RecognitionDoctor(None,task_id="test",device="test")
  error=D.GateError("target_not_stable","observation","reobserve","not ready")
  for _ in range(2):D.require_observation_recovery(d.assess(error))
  with self.assertRaises(D.GateError):D.require_observation_recovery(d.assess(error))
  d.counts.pop("target_not_stable",None)
  report=d.assess(error)
  self.assertEqual(report["repeat"],1)
  D.require_observation_recovery(report)
if __name__=="__main__":unittest.main()
