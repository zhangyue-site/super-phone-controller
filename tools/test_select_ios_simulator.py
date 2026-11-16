import unittest
from select_ios_simulator import select_simulator

class SimulatorSelection(unittest.TestCase):
 def runtime(self,version,**extra):
  return dict(identifier='com.apple.CoreSimulator.SimRuntime.iOS-'+version.replace('.','-'),version=version,isAvailable=True,**extra)
 def devices(self,*versions):
  return {'devices':{self.runtime(v)['identifier']:[dict(name='iPhone test',udid='phone-'+v,isAvailable=True)] for v in versions}}
 def test_newest_runtime_instead_of_first_legacy_device(self):
  self.assertEqual(select_simulator(self.devices('27.0','27.2'),{'runtimes':[self.runtime('27.0'),self.runtime('27.2')]})['udid'],'phone-27.2')
 def test_runtime_and_device_must_both_be_available(self):
  r=self.runtime('27.2');r['isAvailable']=False
  self.assertEqual(select_simulator(self.devices('27.0','27.2'),{'runtimes':[self.runtime('27.0'),r]})['udid'],'phone-27.0')
 def test_missing_runtime_identifier_is_not_usable(self):
  with self.assertRaisesRegex(ValueError,'iOS27 simulator required'):
   select_simulator(self.devices('27.0'),{'runtimes':[dict(version='27.0',isAvailable=True)]})
 def test_no_downgrade_to_older_major_or_other_platform(self):
  with self.assertRaises(ValueError):select_simulator(self.devices('26.0'),{'runtimes':[self.runtime('26.0')]})
  r=self.runtime('27.0');r['identifier']=r['identifier'].replace('.iOS-','.tvOS-')
  with self.assertRaises(ValueError):select_simulator({'devices':{r['identifier']:[dict(name='iPhone test',udid='fake',isAvailable=True)]}},{'runtimes':[r]})
 def test_unavailable_device_and_ipad_are_excluded(self):
  d=self.devices('27.0');entries=next(iter(d['devices'].values()));entries[0]['isAvailable']=False
  entries.append(dict(name='iPad test',udid='pad',isAvailable=True))
  with self.assertRaises(ValueError):select_simulator(d,{'runtimes':[self.runtime('27.0')]})
 def test_numeric_version_order(self):
  self.assertEqual(select_simulator(self.devices('27.2','27.10'),{'runtimes':[self.runtime('27.2'),self.runtime('27.10')]})['udid'],'phone-27.10')

if __name__=='__main__':unittest.main()
