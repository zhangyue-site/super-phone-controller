import tempfile,unittest
from pathlib import Path
from display_service.achai_policy import DateWindow,SaveJournal,Pause
A='a'*64;B='b'*64
class AchaiPolicyTests(unittest.TestCase):
 def test_inclusive_dates_and_both_boundaries(self):
  w=DateWindow('2026-10-21','2026-10-25')
  for day,result in [('2026-10-26','skip_newer'),('2026-10-25','eligible'),('2026-10-21','eligible'),('2026-10-20','pause_before_start')]:self.assertEqual(w.classify(day),result)
 def test_invalid_or_ambiguous_dates_pause(self):
  for d in ('昨天','10-22','2026-02-30','2026-10-25 10:00:00',None):
   with self.subTest(d=d),self.assertRaises(Pause):DateWindow('2026-10-21','2026-10-25').classify(d)
 def test_reversed_window_is_rejected(self):
  with self.assertRaises(ValueError):DateWindow('2026-10-25','2026-10-21')
 def test_pending_survives_restart_and_cannot_repeat(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'state.db';j=SaveJournal(p);j.reserve(A,B);j.close();j=SaveJournal(p)
   self.assertEqual(j.state(A,B),'pending')
   with self.assertRaises(Pause):j.reserve(A,B)
   j.close()
 def test_saved_item_never_reserves_again(self):
  with tempfile.TemporaryDirectory() as d:
   j=SaveJournal(Path(d)/'state.db');j.reserve(A,B);j.verify(A,B,verified=True)
   self.assertEqual(j.state(A,B),'saved')
   with self.assertRaises(Pause):j.reserve(A,B)
   j.close()
 def test_same_order_different_fields_pauses(self):
  with tempfile.TemporaryDirectory() as d:
   j=SaveJournal(Path(d)/'state.db');j.reserve(A,B)
   with self.assertRaises(Pause):j.state(A,'c'*64)
   j.close()
 def test_failed_verification_retains_pending(self):
  with tempfile.TemporaryDirectory() as d:
   j=SaveJournal(Path(d)/'state.db');j.reserve(A,B)
   with self.assertRaises(Pause):j.verify(A,B,verified=False)
   self.assertEqual(j.state(A,B),'pending');j.close()
 def test_verification_cannot_create_a_saved_item(self):
  with tempfile.TemporaryDirectory() as d:
   j=SaveJournal(Path(d)/'state.db')
   with self.assertRaises(Pause):j.verify(A,B,verified=True)
   j.close()
 def test_only_exact_boolean_verification_counts(self):
  with tempfile.TemporaryDirectory() as d:
   j=SaveJournal(Path(d)/'state.db');j.reserve(A,B)
   with self.assertRaises(Pause):j.verify(A,B,verified='true')
   j.close()
