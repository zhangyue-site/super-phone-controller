import unittest,io
from PIL import Image,ImageDraw
from display_service.agent_slider_observation import measure,annotate
class SliderPixels(unittest.TestCase):
 def picture(self,vertical=True):
  im=Image.new("RGB",(300,400),(30,30,30));d=ImageDraw.Draw(im)
  if vertical:d.rectangle((100,100,199,339),fill=(60,60,60));d.rectangle((100,244,199,339),fill=(240,240,240));box=[100,100,200,340]
  else:d.rectangle((20,100,259,199),fill=(60,60,60));d.rectangle((20,100,115,199),fill=(240,240,240));box=[20,100,260,200]
  out=io.BytesIO();im.save(out,"JPEG");return out.getvalue(),box
 def test_vertical_and_horizontal_actual_fill(self):
  for v in (True,False):
   raw,b=self.picture(v);fact=measure(raw,b,300,400);self.assertAlmostEqual(fact["observed_percent"],40,delta=1);self.assertEqual(fact["axis"],"vertical"if v else"horizontal")
 def test_flat_or_wrong_geometry_never_invents_a_thumb(self):
  out=io.BytesIO();Image.new("RGB",(300,400),"white").save(out,"JPEG")
  self.assertIsNone(measure(out.getvalue(),[100,100,200,340],300,400));self.assertIsNone(measure(out.getvalue(),[100,100,200,340],301,400))
 def test_model_supplied_percentage_is_not_trusted(self):
  result=annotate(b"not_image",dict(width=300,height=400),dict(widgets=[dict(role="brightness_slider",bounds=[100,100,200,340],observed_percent=40,observed_source="claimed")]))
  self.assertNotIn("observed_percent",result["widgets"][0])
if __name__=="__main__":unittest.main()
