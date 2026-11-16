import unittest,types,contextlib,io
from display_service.agent_local_observation import wait_for_target,TargetNotStable
B=[1,1,20,20]
def hint(seq,ts,count=None,scope='a',ready=False):
 r=[] if count is None else [dict(id='req-x',label='target',bounds=B,count=count,stableMs=max(0,(count-1)*100),ready=ready)]
 return dict(width=100,height=100,local_observation=dict(scopeHash=scope,sourceSequence=seq,sourceTimestampNs=ts,ageMs=0,regions=r))
class Tests(unittest.TestCase):
 def run_case(self,rows,mutate=False):
  job=types.SimpleNamespace(video_barrier='a'*32,local_observation_capable=True);clock=[0];calls=[];initial=rows[0];pending=iter(rows[1:])
  def read(seq):
   calls.append(seq);clock[0]+=1
   row=next(pending,rows[-1]);
   if mutate:job.video_barrier='b'*32
   return b'x',seq+1,{},row
  with contextlib.redirect_stdout(io.StringIO()) as output:
   with self.assertRaises(TargetNotStable):wait_for_target(job,b'x',1,{},initial,B,'secret-label',read=read,guard=lambda:None,clock=lambda:clock[0],request_id=lambda:'x',budget=3.0)
  self.assertIsNone(job.local_observation_request);self.assertNotIn('secret-label',output.getvalue());self.assertLessEqual(len(calls),3)
  return job.agent_local_stability_failures[-1]
 def test_not_observed_not_claimed_undelivered(self):
  d=self.run_case([hint(1,1),hint(2,100000001),hint(3,200000001),hint(4,300000001)])
  self.assertEqual(d['request_delivery'],'unknown_not_observed');self.assertFalse(d['request_region_observed'])
 def test_consecutive_source_gap(self):
  d=self.run_case([hint(1,1,1),hint(2,300000001,1),hint(3,600000001,1),hint(4,900000001,1)])
  self.assertTrue(d['consecutive_source_gap_observed'])
 def test_transport_gap_not_source_proof(self):
  d=self.run_case([hint(1,1,1),hint(5,400000001,5),hint(9,800000001,9),hint(13,1200000001,1)])
  self.assertFalse(d['consecutive_source_gap_observed']);self.assertTrue(d['transport_snapshot_gap_observed']);self.assertTrue(d['target_counter_reset_observed']);self.assertEqual(d['target_hash_change'],'unknown_not_reported')
 def test_scope(self):
  d=self.run_case([hint(1,1,1),hint(2,100000001,1,scope='b')],True);self.assertEqual(d['reason'],'task_scope_changed');self.assertTrue(d['scope_change_observed'])
 def test_success_unchanged(self):
  job=types.SimpleNamespace(video_barrier='a'*32,local_observation_capable=True)
  h=hint(10,1000000001,10,ready=True);h['local_observation']['regions'][0]['label']='target'
  result=wait_for_target(job,b'x',1,{},h,B,'target',read=lambda _:self.fail(),guard=lambda:None)
  self.assertEqual(result[1],1);self.assertFalse(hasattr(job,'agent_local_stability_failures'))
if __name__=='__main__':unittest.main()
