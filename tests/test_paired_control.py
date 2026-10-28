import concurrent.futures
import threading
import unittest
from display_service.paired_control import Pairings


class PairingsTests(unittest.TestCase):
 def setUp(self):
  self.now=1000.0
  self.parents={'parent':'epaper-01'}
  def parent_device(token):
   if token not in self.parents:raise PermissionError('expired parent')
   return self.parents[token]
  self.p=Pairings(parent_device,clock=lambda:self.now)
 def code(self,parent='parent'):return self.p.issue(parent)['code']
 def ticket(self):return self.p.redeem(self.code())['ticket']
 def test_code_expires_at_exact_120_second_boundary(self):
  code=self.code();self.now+=119.999
  self.assertIn('ticket',self.p.redeem(code))
  code=self.code();self.now+=120
  with self.assertRaises(PermissionError):self.p.redeem(code)
 def test_ticket_expires_at_exact_300_second_boundary(self):
  ticket=self.ticket();self.now+=299.999
  self.assertEqual(self.p.owner(ticket)[3],'epaper-01')
  self.now+=.001
  with self.assertRaises(PermissionError):self.p.owner(ticket)
  with self.assertRaises(PermissionError):self.p.renew(ticket)
 def test_wrong_code_does_not_consume_real_code(self):
  code=self.code()
  with self.assertRaises(PermissionError):self.p.redeem('!'*43)
  wrong=('A' if code[0]!='A' else 'B')+code[1:]
  with self.assertRaises(PermissionError):self.p.redeem(wrong)
  self.assertIn('ticket',self.p.redeem(code))
  with self.assertRaises(PermissionError):self.p.redeem(code)
 def test_concurrent_redemption_has_exactly_one_winner(self):
  code=self.code();barrier=threading.Barrier(2)
  def redeem():
   barrier.wait(timeout=3)
   try:return self.p.redeem(code)['ticket']
   except PermissionError:return None
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
   futures=[pool.submit(redeem) for _ in range(2)]
   results=[f.result(timeout=5) for f in futures]
  self.assertEqual(sum(x is not None for x in results),1)
  self.assertEqual(len(self.p.tickets),1)
 def test_capacity_and_expired_entry_pruning(self):
  for i in range(256):
   parent='parent'+str(i);self.parents[parent]='device'+str(i)
   self.code(parent)
  self.parents['overflow']='overflow'
  with self.assertRaises(ValueError):self.code('overflow')
  self.assertEqual(len(self.p.codes),256)
  self.now+=120;self.code('overflow')
  self.assertEqual(len(self.p.codes),1)
  self.p.codes.clear()
  for _ in range(256):self.ticket()
  with self.assertRaises(ValueError):self.p.redeem(self.code())
  self.assertEqual(len(self.p.tickets),256)
  self.now+=300
  self.assertIn('ticket',self.p.redeem(self.code()))
  self.assertEqual(len(self.p.tickets),1)
 def test_parent_invalidation_and_list_identity_fail_closed(self):
  ticket=self.ticket();identity=self.p.owner(ticket)
  self.assertTrue(self.p.allowed(identity));self.assertTrue(self.p.allowed(list(identity)))
  self.assertFalse(self.p.allowed((identity[0],identity[1],identity[2],'other')))
  code=self.code();self.parents.clear()
  self.assertFalse(self.p.allowed(list(identity)))
  for action in (lambda:self.p.owner(ticket),lambda:self.p.renew(ticket),lambda:self.p.redeem(code)):
   with self.assertRaises(PermissionError):action()
 def test_renew_retains_identity_and_revoke_removes_codes_and_tickets(self):
  ticket=self.ticket();identity=self.p.owner(ticket);self.now+=299
  self.p.renew(ticket);self.now+=1
  self.assertEqual(self.p.owner(ticket),identity)
  code=self.code();self.p.revoke('parent')
  with self.assertRaises(PermissionError):self.p.owner(ticket)
  with self.assertRaises(PermissionError):self.p.redeem(code)
  self.assertEqual((self.p.codes,self.p.tickets),({},{}))

if __name__=='__main__':unittest.main()
