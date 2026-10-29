import unittest,os
from unittest.mock import patch
from display_service.jev_vision import launcher_observation
from display_service import general_vision
from test_wechat_nav import frame

class LauncherGateTests(unittest.TestCase):
 def value(self,page='launcher',confidence=.99,safe=.99):
  return {'answers':{'page':{'type':'choice','choice':page,'confidence':confidence,'probabilities':{'launcher':1. if page=='launcher' else 0.,'other':0. if page=='launcher' else 1.}},'can_open_drawer':{'type':'noul','noul':safe}}}
 def test_gate_only_produces_checked_blank_swipe_not_app_click(self):
  r=launcher_observation(self.value(),True);self.assertEqual(r['action'],'drag');self.assertEqual(r['bounds'],[450,630,550,670]);self.assertEqual(r['end'],[500,250]);self.assertTrue(r['_trusted_launcher_blank'])
 def test_other_page_blank_failure_and_low_confidence_do_not_authorize(self):
  for value,clear in [(self.value(page='other'),True),(self.value(),False)]:
   with self.subTest(value=value):self.assertIsNone(launcher_observation(value,clear))
 def test_unknown_page_fails_closed_but_optional_scores_are_not_permission(self):
  v=self.value();v['answers']['page']['choice']='unknown'
  with self.assertRaises(ValueError):launcher_observation(v,True)
  v=self.value(confidence=0);v['answers']['page']['probabilities']={'malformed':'diagnostic'}
  self.assertEqual(launcher_observation(v,True)['action'],'drag')
 def test_generic_app_gets_gateway_before_any_mimo_location(self):
  gate=launcher_observation(self.value(),True)
  with patch.dict(os.environ,{'EPAPER_NAV_JUDGE':'jev'}),patch('display_service.jev_vision.observe_launcher',return_value=gate) as probe,patch('display_service.jev_vision.clear_swipe_region',return_value=False),patch.object(general_vision,'vision_route',side_effect=AssertionError('must not locate app before drawer')):
   self.assertEqual(general_vision.observe(frame(0),'打开计算器'),gate);probe.assert_called_once()
 def test_final_verification_never_uses_desktop_gateway(self):
  with patch.dict(os.environ,{'EPAPER_NAV_JUDGE':'jev'}),patch('display_service.jev_vision.observe_launcher') as probe,patch.object(general_vision,'vision_route',side_effect=ValueError('synthetic-stop')):
   with self.assertRaisesRegex(ValueError,'synthetic-stop'):general_vision.observe(frame(0),'打开计算器',verify=True)
   probe.assert_not_called()
