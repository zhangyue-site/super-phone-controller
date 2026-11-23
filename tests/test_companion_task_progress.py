import unittest
from display_service.dialogue import Mailbox
from display_service.task_progress import task_progress,mark_progress
class ProgressTests(unittest.TestCase):
 def test_true_task_sequence_and_rounds(self):
  m=Mailbox();j=m.create('board','aaaaaaaaaaaaaaaa',1)
  r={'state':'running','verified':False}
  self.assertEqual(task_progress(r,j)['phase'],'unknown')
  mark_progress(j,'recognizing');self.assertEqual(task_progress(r,j)['phase'],'recognizing')
  m.offer(j,{'op':'hid_home'});self.assertEqual(task_progress(r,j)['phase'],'dispatching')
  command=m.poll(j.device,j.session,j.sequence);self.assertEqual(task_progress(r,j)['phase'],'operating')
  m.ack(j.device,j.session,j.sequence,command['id'],True,'HID_HOME_REPORT_SENT')
  self.assertNotEqual(task_progress(r,j)['phase'],'done')
  mark_progress(j,'recognizing');self.assertEqual(task_progress(r,j)['round'],2)
  self.assertEqual(task_progress(r,j)['completed']&48,0)
  mark_progress(j,'verifying');self.assertEqual(task_progress(r,j)['phase'],'verifying')
  self.assertNotEqual(task_progress({'state':'done','verified':False},j)['phase'],'done')
  self.assertEqual(task_progress({'state':'done','verified':True},j)['phase'],'done')
 def test_no_job_no_fabricated_recognition(self):
  p=task_progress({'state':'running'},None)
  self.assertEqual(p['phase'],'unknown');self.assertEqual(p['completed'],7)
 def test_terminal_dominates_late_activity(self):
  m=Mailbox();j=m.create('board','bbbbbbbbbbbbbbbb',1);mark_progress(j,'operating')
  self.assertEqual(task_progress({'state':'stopped'},j)['phase'],'stopped')
  self.assertEqual(task_progress({'state':'error'},j)['phase'],'error')
if __name__=='__main__':unittest.main()
