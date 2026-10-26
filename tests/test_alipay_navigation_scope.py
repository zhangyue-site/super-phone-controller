import unittest
from display_service.general_nav import parse_task,GeneralNavigator
class AlipayScope(unittest.TestCase):
 def test_app_name_is_not_a_payment_action(self):
  self.assertEqual(parse_task('打开支付宝'),'打开支付宝')
  for task in ('打开支付宝付款','打开支付宝转账','进入支付宝并支付','支付100元'):
   self.assertIsNone(parse_task(task))
 def test_only_exact_app_label_is_exempt(self):
  n=GeneralNavigator(None,None)
  o={'action':'click','safe':True,'target_label':'支付宝','bounds':[10,100,100,200]}
  self.assertEqual(n._command(o,'打开支付宝')['op'],'hid_pointer')
  for label in ('支付','支付宝付款','转账'):
   with self.assertRaises(ValueError):n._command(dict(o,target_label=label),'打开支付宝')
