import io,json,time,unittest,urllib.request
from unittest.mock import patch
from PIL import Image
from display_service.general_vision import observe

class VisionOutputContractTests(unittest.TestCase):
 def test_navigation_and_verification_are_compact_and_nonreasoning(self):
  image=io.BytesIO();Image.new('RGB',(10,10)).save(image,format='JPEG')
  for verify,budget in [(False,400),(True,500)]:
   captured=[]
   def request(payload,provider,model,cfg):
    captured.append(payload)
    observation={'coordinate_system':'pixels','confidence':0,'safe':False,'complete':False,'action':'unknown','verified':False}
    value={'choices':[{'message':{'content':json.dumps(observation)},'finish_reason':'stop'}]}
    return value,urllib.request.Request('https://synthetic.invalid'),provider,time.monotonic()
   with self.subTest(verify=verify),patch('display_service.general_vision.vision_route',return_value=('opencode-go','mimo-v2.6-flash',{})),patch('display_service.general_vision.request_vision',side_effect=request):
    observe(image.getvalue(),'打开支付宝',verify=verify)
    self.assertEqual(captured[0]['thinking'],{'type':'disabled'})
    self.assertEqual(captured[0]['max_tokens'],budget)
    self.assertEqual(captured[0]['response_format'],{'type':'json_object'})
    self.assertIn('紧凑JSON',captured[0]['messages'][0]['content'])
