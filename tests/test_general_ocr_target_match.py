import io,json,unittest
from unittest.mock import patch
from PIL import Image
from display_service import general_ocr as m
class Tests(unittest.TestCase):
 def setUp(self):
  out=io.BytesIO();Image.new('RGB',(588,1280),'white').save(out,'JPEG');self.raw=out.getvalue()
 def read(self,hit,task='打开支付宝账单'):
  with patch.object(m,'_TOKEN_FILE',''),patch.object(m.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps({'hit':hit}).encode())):
   return m.ocr_observe(self.raw,task)
 def test_actual_wrong_fuzzy_match_with_perfect_ocr_confidence_is_rejected(self):
  self.assertIsNone(self.read({'text':'创建清单','score':1.0,'bounds':[98,92,228,130]}))
 def test_exact_unique_word_can_still_be_located(self):
  r=self.read({'text':'支付宝','score':.99,'bounds':[100,200,200,230]},'打开支付宝');self.assertEqual(r['target_label'],'支付宝')
 def test_substrings_and_added_actions_are_not_exact_targets(self):
  for label in ('支付宝服务','支付宝账单 保存','账单','完成'):
   self.assertIsNone(self.read({'text':label,'score':1.,'bounds':[10,20,100,50]}))
 def test_invalid_geometry_never_becomes_a_click(self):
  for b in ([0,0,0,10],[-1,10,50,30],[0,0,589,20],[0,0,10.5,20],[False,0,10,20],None):
   self.assertIsNone(self.read({'text':'支付宝账单','score':1.,'bounds':b}))
 def test_nonfinite_or_non_numeric_confidence_is_rejected(self):
  for score in (float('nan'),float('inf'),'1.0',True):
   self.assertIsNone(self.read({'text':'支付宝账单','score':score,'bounds':[10,20,50,60]}))
if __name__=='__main__':unittest.main()
