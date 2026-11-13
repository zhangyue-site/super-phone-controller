import unittest
from display_service.cloud_progress import summary
class CloudProgressTests(unittest.TestCase):
 def test_ack_is_not_success_and_no_private_content(self):
  out=summary('task','android-app','ack',True)
  self.assertFalse(out['verified']);self.assertFalse(out['terminal'])
  self.assertNotIn('percent',out);self.assertIn('updatedAt',out)
 def test_timestamp_changes_only_on_observed_change(self):
  a=summary('stable','telegram','queued');b=summary('stable','telegram','queued')
  self.assertEqual(a['updatedAt'],b['updatedAt'])
