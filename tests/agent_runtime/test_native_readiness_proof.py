import importlib.util,unittest,copy
from pathlib import Path
from display_service import local_observation as m
def fact(required,count,ready,ms=600):
 return dict(v=1,scopeHash='a'*64,sourceSequence=20,sourceTimestampNs=1000000000,sourceWidth=100,sourceHeight=100,ageMs=10,requiredFrames=required,minStableMs=600,regions=[dict(id='r',label='目标',role='agent_target',bounds=[10,10,30,30],count=count,stableMs=ms,ready=ready)],layoutHints=[])
class Proof(unittest.TestCase):
 def test_native_threshold_and_ready_are_both_required(self):
  for required,count,ready,expected in ((10,5,False,False),(10,5,True,False),(10,10,False,False),(10,10,True,True),(4,4,True,True),(4,4,False,False)):
   with self.subTest(required=required,count=count,ready=ready):
    d=m.validate(fact(required,count,ready),100,100);self.assertEqual(d['regions'][0]['ready'],expected)
    self.assertEqual(m.ready_region(dict(local_observation=d),[10,10,30,30],label='目标'),expected)
 def test_short_duration_is_not_ready(self):self.assertFalse(m.validate(fact(10,10,True,599),100,100)['regions'][0]['ready'])
 def test_float_protocol_is_rejected(self):self.assertIsNone(m.validate(fact(10.0,10,True),100,100))
