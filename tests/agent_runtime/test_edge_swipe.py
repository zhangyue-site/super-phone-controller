import unittest
from display_service.agent_runtime import _locate
from display_service.agent_capabilities import catalog
from display_service.agent_integration import policy
class EdgeSwipe(unittest.TestCase):
 def step(self,edge='top'):
  return dict(capability='edge_swipe',target='展开系统面板',locator='edge',bounds=None,edge=edge,anchor_percent=80,distance_percent=60)
 def hint(self):return dict(width=588,height=1280,lines=[])
 def test_top_edge_starts_at_real_top_not_twenty_percent(self):
  command,bounds=_locate(self.step(),self.hint());self.assertEqual(command['op'],'hid_pointer');self.assertEqual(command['kind'],'drag');self.assertLess(command['y'],32767*.01);self.assertAlmostEqual(command['x']/32767,.8,delta=.01);self.assertGreater(command['y2'],32767*.5)
 def test_bottom_left_right_use_current_geometry(self):
  bottom,_=_locate(self.step('bottom'),self.hint());self.assertGreater(bottom['y'],32767*.99);self.assertLess(bottom['y2'],bottom['y'])
  left,_=_locate(self.step('left'),self.hint());self.assertLess(left['x'],32767*.01);self.assertGreater(left['x2'],left['x'])
  right,_=_locate(self.step('right'),self.hint());self.assertGreater(right['x'],32767*.99);self.assertLess(right['x2'],right['x'])
 def test_model_cannot_supply_arbitrary_start_or_endpoint(self):
  for extra in [dict(bounds=[0,0,100,100]),dict(end=[500,500]),dict(anchor_percent=True),dict(distance_percent=99),dict(edge='corner')]:
   with self.assertRaises(ValueError):_locate(dict(self.step(),**extra),self.hint())
 def test_edge_cannot_bypass_restricted_target_rules(self):
  for target in ['同意','立即支付','授权登录','删除']:
   step=dict(self.step(),target=target)
   with self.assertRaises(ValueError):_locate(step,self.hint())
   self.assertFalse(policy(dict(_platform='android',original='请打开控制中心'),step,self.hint()))
 def test_only_android_catalog_and_policy_offer_this_tested_tool(self):
  self.assertIn('edge_swipe',catalog('android')['tools']);self.assertNotIn('edge_swipe',catalog('ios')['tools']);self.assertNotIn('edge_swipe',catalog('unknown')['tools'])
  self.assertTrue(policy(dict(_platform='android',original='请打开控制中心'),self.step(),self.hint()));self.assertFalse(policy(dict(_platform='ios',original='请打开控制中心'),self.step(),self.hint()))
if __name__=='__main__':unittest.main()
