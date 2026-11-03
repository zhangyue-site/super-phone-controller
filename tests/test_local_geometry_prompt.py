"""Geometry observations remain advisory and never contaminate verification."""
import io,json,unittest
from unittest.mock import patch
from PIL import Image
from display_service import general_vision as v

class LocalGeometryPromptTests(unittest.TestCase):
 def setUp(self):
  stream=io.BytesIO();Image.new("RGB",(100,200)).save(stream,"JPEG");self.jpeg=stream.getvalue()
 def observe(self,verify=False):
  captured=[]
  def request(payload,*args):
   captured.append(payload)
   result={"coordinate_system":"pixels","safe":True,"complete":False,"action":"unknown","bounds":[1,1,4,4]}
   return {"choices":[{"finish_reason":"stop","message":{"content":json.dumps(result)}}]},type("Request",(),{"get_header":lambda *a:None})(),"opencode-go",__import__("time").monotonic()
  with patch.object(v,"vision_route",return_value=("opencode-go","test",{})),patch.object(v,"request_vision",side_effect=request),patch.object(v,"launcher_method",side_effect=lambda r,*a:r):
   v.observe(self.jpeg,"查找一个安全页面",verify)
  return captured[0]["messages"][1]["content"][0]["text"]
 def test_geometry_advisory_only_in_planning_and_context_resets(self):
  hint={"boxes":[{"x":.1,"y":.2,"width":.3,"height":.4,"score":.8}],"task_id":"untrusted"}
  with v.button_geometry_context(hint):
   text=self.observe();self.assertIn("local_button_geometry",text);self.assertIn("[10,40,40,120]",text.replace(" ",""))
   self.assertNotIn("local_button_geometry",self.observe(verify=True))
  self.assertNotIn("local_button_geometry",self.observe())
 def test_malformed_and_text_cannot_enter_geometry_prompt(self):
  for hint in [{"boxes":[{"x":float("nan"),"y":0,"width":1,"height":1,"score":1}]},{"boxes":[{"x":0,"y":0,"width":1,"height":1,"score":"send money"}]}]:
   with v.button_geometry_context(hint):self.assertNotIn("local_button_geometry",self.observe())

 def test_ios_platform_metadata_is_bounded_and_context_local(self):
  with v.phone_platform_context('ios'):
   self.assertIn('当前手机系统：iOS',self.observe())
  self.assertNotIn('当前手机系统：iOS',self.observe())
  with self.assertRaises(ValueError):
   with v.phone_platform_context('execute shell'):pass
