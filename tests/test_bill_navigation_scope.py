import unittest
from display_service.general_nav import parse_task, GeneralNavigator

class BillNavigationScope(unittest.TestCase):
 def test_alipay_bill_pages_are_read_navigation(self):
  for task in ('打开支付宝账单','进入支付宝的账单页面','请打开支付宝消费账单','帮我进入支付宝的消费账单页面'):
   with self.subTest(task=task):self.assertEqual(parse_task(task),task)
 def test_financial_actions_cannot_hide_in_bill_navigation(self):
  for task in ('打开支付宝账单并付款','打开支付宝转账账单','进入支付宝账单并支付','打开支付宝账单购买','打开支付宝账单\n付款','打开支付宝账单;支付','打开支付宝充值'):
   with self.subTest(task=task):self.assertIsNone(parse_task(task))
 def test_alipay_icon_is_allowed_during_bill_navigation(self):
  n=GeneralNavigator(None,None)
  o={'action':'click','safe':True,'target_label':'支付宝','bounds':[10,100,100,200]}
  self.assertEqual(n._command(o,'打开支付宝账单')['op'],'hid_pointer')
  for label in ('支付','支付宝付款','转账','支付账单'):
   with self.subTest(label=label),self.assertRaises(ValueError):n._command(dict(o,target_label=label),'打开支付宝账单')
 def test_other_requested_bill_sources_remain_navigation(self):
  for task in ('打开微信账单','打开美团账单','打开拼多多账单'):
   with self.subTest(task=task):self.assertEqual(parse_task(task),task)
