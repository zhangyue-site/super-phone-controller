import unittest
from types import SimpleNamespace
from display_service.agent_local_observation import wait_for_target,TargetNotStable
class Protocol(unittest.TestCase):
 def test_reported_threshold_is_sent_without_relabeling_ready(self):
  for threshold in (4,10):
   j=SimpleNamespace(video_barrier='a'*32,local_observation_capable=True)
   h=dict(width=200,height=400,local_observation=dict(requiredFrames=threshold,regions=[]))
   seen=[]
   def read(seq):
    seen.append(j.local_observation_request.copy());return b'raw',seq,None,h
   with self.assertRaises(TargetNotStable):wait_for_target(j,b'raw',1,None,h,[10,10,30,30],'目标',read=read,guard=lambda:None)
   self.assertEqual(seen[0]['requiredFrames'],threshold);self.assertIsNone(j.local_observation_request)
 def test_no_report_defaults_to_native_v1_ten(self):
  j=SimpleNamespace(video_barrier='a'*32,local_observation_capable=True);h=dict(width=200,height=400);seen=[]
  def read(seq):seen.append(j.local_observation_request.copy());return b'raw',seq,None,h
  with self.assertRaises(TargetNotStable):wait_for_target(j,b'raw',1,None,h,[10,10,30,30],'目标',read=read,guard=lambda:None)
  self.assertEqual(seen[0]['requiredFrames'],10)
