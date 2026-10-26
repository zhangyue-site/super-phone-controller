import unittest,os
from types import SimpleNamespace
from unittest.mock import patch
from display_service import app_screen
class LongScreenTests(unittest.TestCase):
 def test_only_explicit_target_existing_screen_ticket_extends(self):
  authority=SimpleNamespace(clock=lambda:100,tickets={'valid':(400,'epaper-01','hash')})
  with patch.object(app_screen,'AUTHORITY',authority),patch.dict(os.environ,{'EPAPER_SCREEN_DIAG_LONG':'epaper-01'}):
   grant={'ticket':'valid','expiresIn':300};app_screen.extend_diagnostic_ticket('epaper-01',grant)
   self.assertEqual(authority.tickets['valid'],(1300,'epaper-01','hash'));self.assertEqual(grant['expiresIn'],1200)
   with self.assertRaises(ValueError):app_screen.extend_diagnostic_ticket('epaper-01',{'ticket':'unknown'})
 def test_default_and_other_device_keep_short_tickets(self):
  authority=SimpleNamespace(clock=lambda:100,tickets={'valid':(400,'other','hash')})
  with patch.object(app_screen,'AUTHORITY',authority),patch.dict(os.environ,{'EPAPER_SCREEN_DIAG_LONG':'epaper-01'}):
   grant={'ticket':'valid','expiresIn':300};app_screen.extend_diagnostic_ticket('other',grant)
   self.assertEqual(grant['expiresIn'],300);self.assertEqual(authority.tickets['valid'][0],400)
