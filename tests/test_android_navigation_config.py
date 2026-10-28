import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

class NavigationConfigTests(unittest.TestCase):
 def test_main_activity_handles_external_input_navigation_change(self):
  root=ET.parse(Path(__file__).resolve().parents[1]/"app/android/app/src/main/AndroidManifest.xml").getroot()
  android="{http://schemas.android.com/apk/res/android}"
  activity=next(a for a in root.findall("./application/activity") if a.get(android+"name")==".MainActivity")
  self.assertIn("navigation",activity.get(android+"configChanges","").split("|"))
