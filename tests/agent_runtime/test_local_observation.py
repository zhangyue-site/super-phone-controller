import unittest,copy,io,hashlib
from PIL import Image
from display_service.phone_ocr import validate
class LocalObservation(unittest.TestCase):
 def setUp(self):
  out=io.BytesIO();Image.new('RGB',(200,400),'white').save(out,format='JPEG');self.raw=out.getvalue()
  self.local=dict(v=1,scopeHash='a'*64,sourceSequence=20,sourceTimestampNs=2000000000,sourceWidth=200,sourceHeight=400,ageMs=50,requiredFrames=10,minStableMs=600,regions=[dict(id='r1',label='跳过广告',role='ad_skip_candidate',bounds=[100,20,180,50],count=10,stableMs=900,ready=True)],layoutHints=[])
  self.ocr=dict(v=2,width=200,height=400,ageMs=100,sha256=hashlib.sha256(self.raw).hexdigest(),lines=[dict(text='跳过广告',bounds=[100,20,180,50])],local=self.local)
 def test_new_observation_is_bound_to_authorized_jpeg(self):
  result=validate(self.ocr,self.raw);self.assertIsNotNone(result);self.assertTrue(result['local_observation']['regions'][0]['ready'])
  wrong=copy.deepcopy(self.ocr);wrong['sha256']='b'*64;self.assertIsNone(validate(wrong,self.raw))
 def test_old_ocr_version_remains_compatible(self):
  old={k:v for k,v in self.ocr.items() if k!='local'};old['v']=1;self.assertIsNotNone(validate(old,self.raw))
 def test_cached_claim_cannot_mark_one_sample_ready(self):
  self.local['regions'][0]['count']=1
  result=validate(self.ocr,self.raw);self.assertFalse(result['local_observation']['regions'][0]['ready'])
 def test_invalid_region_does_not_create_local_capability(self):
  self.local['regions'][0]['bounds']=[0,0,999,999]
  result=validate(self.ocr,self.raw);self.assertIsNotNone(result);self.assertNotIn('local_observation',result)
 def test_ten_frames_too_short_is_not_ready(self):
  self.local['regions'][0]['stableMs']=50
  result=validate(self.ocr,self.raw);self.assertFalse(result['local_observation']['regions'][0]['ready'])
if __name__=='__main__':unittest.main()
