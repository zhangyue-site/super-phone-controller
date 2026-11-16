import unittest,copy
from types import SimpleNamespace as N
from display_service.agent_local_observation import wait_for_target,TargetNotStable
class Wait(unittest.TestCase):
 def hint(self,count=1,ms=0,id='ocr-1'):
  return dict(width=200,height=400,lines=[],local_observation=dict(ageMs=10,regions=[dict(id=id,label='我的',role='text_candidate',bounds=[10,20,90,50],count=count,stableMs=ms,ready=count>=10 and ms>=600)]))
 def test_legacy_ocr_does_not_claim_local_stability_or_wait(self):
  job=N(video_barrier='a'*32);calls=[]
  result=wait_for_target(job,b'image',1,{},dict(width=200,height=400,lines=[]),[10,20,90,50],'我的',read=lambda *a:calls.append(1),guard=lambda:None)
  self.assertEqual(result[1],1);self.assertFalse(calls);self.assertFalse(hasattr(job,'local_observation_request'))
 def test_waits_for_real_report_then_clears_own_request(self):
  job=N(video_barrier='a'*32);calls=[]
  def read(after):
   calls.append(after);ident=job.local_observation_request['regions'][0]['id'];return b'new',after+1,{},self.hint(9 if len(calls)==1 else 10,800,id=ident)
  result=wait_for_target(job,b'image',1,{},self.hint(),[10,20,90,50],'我的',read=read,guard=lambda:None,request_id=lambda:'b'*32)
  self.assertEqual(len(calls),2);self.assertEqual(result[1],3);self.assertIsNone(job.local_observation_request)
 def test_already_ready_does_not_request_again(self):
  job=N(video_barrier='a'*32)
  result=wait_for_target(job,b'image',1,{},self.hint(10,900),[10,20,90,50],'我的',read=lambda *a:self.fail('unexpected read'),guard=lambda:None)
  self.assertEqual(result[1],1)
 def test_revocation_does_not_continue_sampling(self):
  job=N(video_barrier='a'*32)
  def deny():raise PermissionError('revoked')
  with self.assertRaises(PermissionError):wait_for_target(job,b'image',1,{},self.hint(),[10,20,90,50],'我的',read=lambda *a:self.fail('read after revocation'),guard=deny)
 def test_insufficient_fresh_frames_times_out_without_input(self):
  job=N(video_barrier='a'*32);t=[0.]
  def clock():t[0]+=.5;return t[0]
  def read(after):return b'new',after+1,{},self.hint(1,0,id=job.local_observation_request['regions'][0]['id'])
  with self.assertRaises(TargetNotStable):wait_for_target(job,b'image',1,{},self.hint(),[10,20,90,50],'我的',read=read,guard=lambda:None,clock=clock)
  self.assertIsNone(job.local_observation_request)
if __name__=='__main__':unittest.main()
