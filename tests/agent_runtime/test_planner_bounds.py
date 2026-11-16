import unittest
from unittest.mock import patch
from display_service import agent_runtime as r
from display_service.agent_gates import GateError
from display_service.agent_doctor import require_observation_recovery
from display_service.agent_contract import Authority
from display_service.agent_observation import capture,bind_visual
import test_gesture_runtime as fixture

class PlannerBounds(unittest.TestCase):
 def locate(self,bounds,width=588,height=1280):
  a=Authority('t','d','s','l',frozenset({'observe'}),100)
  hint=capture(a,1,b'synthetic frame',dict(width=width,height=height,source='phone-ocr',lines=[]),observed_at=1).hint()
  visual=bind_visual(hint,dict(scene='launcher',widgets=[],regions=[dict(role='scroll_container',bounds=[0,0,width,height])]))
  step=dict(capability='page',target='桌面应用网格',locator='region',bounds=bounds,direction='up',end=None)
  return r._locate(step,hint,visual_evidence=visual)
 def test_observed_small_pixel_container_requests_reobservation(self):
  with self.assertRaises(GateError) as got:self.locate([0,850,588,1010])
  self.assertEqual(got.exception.code,'gesture_invalid');self.assertEqual(got.exception.recovery,'reobserve')
 def test_valid_pixel_coordinate_over_1000_is_not_mistaken_for_normalized_box(self):
  command,origin=self.locate([0,100,588,1200]);self.assertEqual(command['op'],'hid_pointer');self.assertEqual(len(origin),4)
 def test_geometry_is_rejected_before_input_and_never_clamped(self):
  bounds=[0,850,588,1010];original=list(bounds)
  with self.assertRaises(GateError):self.locate(bounds)
  self.assertEqual(bounds,original)
 def test_write_capability_is_not_made_retryable(self):
  with self.assertRaises(GateError) as got:r._locate(dict(capability='save_record',target='save',locator='region',bounds=[0,0,1001,1001]),{})
  self.assertNotEqual(got.exception.code,'gesture_invalid');self.assertEqual(got.exception.recovery,'stop')
 def test_unexpected_programming_error_stays_terminal(self):
  with patch.object(r,'_locate_impl',side_effect=TypeError('synthetic internal defect')):
   with self.assertRaises(GateError) as got:r._locate(dict(capability='page',bounds=[0,1,2,3]),{})
  self.assertEqual(got.exception.code,'tool_arguments_invalid');self.assertEqual(got.exception.recovery,'stop')
 def test_three_invalid_replans_stop_without_relaxing_gate(self):
  require_observation_recovery(dict(code='gesture_invalid',repeat=2,recovery='refresh_visual'))
  with self.assertRaises(GateError) as got:require_observation_recovery(dict(code='gesture_invalid',repeat=3,recovery='refresh_visual'))
  self.assertEqual(got.exception.code,'planner_geometry_blocked');self.assertEqual(got.exception.recovery,'stop')
 def test_runtime_stops_after_three_bad_proposals_with_zero_input(self):
  waited,sent,validated,outcome=fixture.Runtime().run_case(first_invalid=True,invalid_count=3)
  self.assertEqual(sent,[]);self.assertFalse(outcome['verified']);self.assertEqual(outcome['failure']['code'],'planner_geometry_blocked')
 def test_runtime_reads_again_then_sends_only_validated_new_plan(self):
  waited,sent,validated,outcome=fixture.Runtime().run_case(first_invalid=True)
  self.assertTrue(outcome['verified'],outcome);self.assertEqual(len(sent),1);self.assertEqual(validated,[True]);self.assertTrue(waited)

if __name__=='__main__':unittest.main()
