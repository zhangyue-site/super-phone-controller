import io,unittest
from PIL import Image,ImageDraw
from display_service.general_nav import verification_region
from display_service.skill_engine import region_matches

def raw(im):
 out=io.BytesIO();im.save(out,format='PNG');return out.getvalue()
class StableResult(unittest.TestCase):
 def test_status_clock_only_does_not_invalidate_result(self):
  a=Image.new('RGB',(640,1280),'white');b=a.copy();ImageDraw.Draw(b).rectangle((0,0,400,40),fill='black')
  self.assertTrue(region_matches(verification_region(raw(a),[0,0,1000,1000]),raw(b)))
 def test_changed_application_content_still_rejected(self):
  a=Image.new('RGB',(640,1280),'white');b=a.copy();ImageDraw.Draw(b).rectangle((100,300,400,700),fill='black')
  self.assertFalse(region_matches(verification_region(raw(a),[0,0,1000,1000]),raw(b)))
 def test_system_bar_alone_is_not_goal_evidence(self):
  with self.assertRaises(ValueError):verification_region(raw(Image.new('RGB',(640,1280),'white')),[0,0,1000,30])
