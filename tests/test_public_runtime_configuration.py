import os,unittest
from unittest.mock import patch
from display_service.voice import asr_script
from display_service.jev_vision import proxy_settings
class RuntimeConfigurationTests(unittest.TestCase):
 def test_unconfigured_recognition_has_no_private_fallback(self):
  with patch.dict(os.environ,{},clear=True):
   with self.assertRaisesRegex(RuntimeError,'EPAPER_ASR'):asr_script()
 def test_operator_configures_the_recognition_adapter(self):
  with patch.dict(os.environ,{'EPAPER_ASR':'/srv/example-adapter/asr.py'},clear=True):
   self.assertEqual(asr_script(),'/srv/example-adapter/asr.py')
 def test_empty_recognition_setting_does_not_run_a_hidden_adapter(self):
  with patch.dict(os.environ,{'EPAPER_ASR':'  '},clear=True):
   with self.assertRaises(RuntimeError):asr_script()
 def test_proxy_is_opt_in_not_a_private_local_service(self):
  with patch.dict(os.environ,{},clear=True):self.assertEqual(proxy_settings(),{})
 def test_operator_configured_proxy_is_used(self):
  with patch.dict(os.environ,{'EPAPER_JEV_PROXY':'http://proxy.example:8080'},clear=True):self.assertEqual(proxy_settings(),{'https':'http://proxy.example:8080'})
if __name__=='__main__':unittest.main()
