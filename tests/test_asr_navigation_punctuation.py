import unittest
from display_service.conversation import normalize_navigation_text
class Punctuation(unittest.TestCase):
 def test_asr_terminal_period(self):self.assertEqual(normalize_navigation_text('打开设置。'),'打开设置')
 def test_contact_internal_punctuation(self):self.assertEqual(normalize_navigation_text('打开微信找到李.洋。'),'打开微信找到李.洋')
 def test_chat_is_unchanged(self):self.assertEqual(normalize_navigation_text('你觉得怎么样？'),'你觉得怎么样？')
