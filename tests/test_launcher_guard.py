import io,unittest
from PIL import Image,ImageDraw
from display_service.skill_engine import signature
from display_service.launcher_guard import same_launcher_structure
from display_service.general_nav import GeneralNavigator
from display_service.wechat_nav import WechatNavigator
class LauncherGuardTests(unittest.TestCase):
 def frame(self,shade=60,move=0,popup=False):
  im=Image.new('RGB',(640,1280),(shade,shade,shade));d=ImageDraw.Draw(im)
  for x in [60,180,300,420,540]:d.rectangle((x+move,950,x+55+move,1000),fill='white')
  if popup:d.rectangle((100,400,540,800),fill='white')
  b=io.BytesIO();im.save(b,format='PNG');return b.getvalue()
 def test_background_only_can_match_structure(self):
  self.assertTrue(same_launcher_structure(signature(self.frame(60)),signature(self.frame(70))))
 def test_moved_icons_and_popup_are_rejected(self):
  a=signature(self.frame())
  self.assertFalse(same_launcher_structure(a,signature(self.frame(move=50))))
  self.assertFalse(same_launcher_structure(a,signature(self.frame(popup=True))))
 def test_only_certified_general_gesture_can_use_structure(self):
  old=signature(self.frame(60));newraw=self.frame(70);new=signature(newraw)
  nav=GeneralNavigator(None,None)
  self.assertFalse(nav._matches_action_frame(old,new,newraw))
  self.assertFalse(WechatNavigator(None,None)._matches_action_frame(dict(old,_blank_launcher=True),new,newraw))
  self.assertTrue(nav._matches_action_frame(dict(old,_blank_launcher=True),new,newraw))
 def test_model_cannot_forge_internal_launcher_marker(self):
  from display_service.general_vision import normalize_observation
  self.assertNotIn('_trusted_launcher_blank',normalize_observation({'coordinate_system':'pixels','_trusted_launcher_blank':True},640,1280))

 def test_visible_settings_requires_unchanged_icon_pixels(self):
  from display_service.skill_engine import region
  raw=self.frame(60);changed=self.frame(70);expected=signature(raw);expected['_launcher_settings']=True
  nav=GeneralNavigator(None,None)
  self.assertFalse(nav._matches_action_frame(expected,signature(changed),changed))
  expected['settings_core']=region(raw,[100,750,150,775])
  self.assertTrue(nav._matches_action_frame(expected,signature(changed),changed))
  im=Image.open(io.BytesIO(changed));ImageDraw.Draw(im).rectangle((70,960,90,980),fill='red');b=io.BytesIO();im.save(b,format='PNG');other=b.getvalue()
  self.assertFalse(nav._matches_action_frame(expected,signature(other),other))
 def test_model_cannot_forge_settings_marker(self):
  from display_service.general_vision import normalize_observation
  self.assertNotIn('_trusted_launcher_settings',normalize_observation({'coordinate_system':'pixels','_trusted_launcher_settings':True},640,1280))

 def test_round_icon_background_changes_but_core_stays_fixed(self):
  from display_service.launcher_guard import settings_icon_core
  def image(shade):
   im=Image.new('RGB',(640,1280),(shade,shade,shade));d=ImageDraw.Draw(im);d.ellipse((100,900,180,980),fill='blue');d.rectangle((40,100,300,130),fill='white');d.rectangle((400,1000,460,1050),fill='white');d.rectangle((130,925,150,955),fill='white');b=io.BytesIO();im.save(b,format='PNG');return b.getvalue()
  a,b=image(60),image(70);bounds=[156,703,282,766];expected=signature(a);expected.update(_launcher_settings=True,settings_core=settings_icon_core(a,bounds))
  self.assertTrue(GeneralNavigator(None,None)._matches_action_frame(expected,signature(b),b))
  for invalid in [[0,0,1000,1000],[100,100,101,101]]:
   with self.assertRaises(ValueError):settings_icon_core(a,invalid)

 def test_weak_wallpaper_texture_is_not_a_control_anchor(self):
  def image(offset):
   im=Image.new('RGB',(640,1280));d=ImageDraw.Draw(im)
   for y in range(1280):
    shade=40+((y+offset)//24%2)*12;d.line((0,y,639,y),fill=(shade,shade,shade))
   for x in [60,180,300,420,540]:d.rectangle((x,950,x+55,1000),fill='white')
   b=io.BytesIO();im.save(b,format='PNG');return b.getvalue()
  self.assertTrue(same_launcher_structure(signature(image(0)),signature(image(12))))
 def test_featureless_frame_cannot_pass_structure_fence(self):
  im=Image.new('RGB',(640,1280),(60,60,60));b=io.BytesIO();im.save(b,format='PNG');sig=signature(b.getvalue())
  self.assertFalse(same_launcher_structure(sig,sig))

 def test_tiny_compression_noise_is_bounded_but_changed_glyph_fails(self):
  from display_service.launcher_guard import quantized_core_matches
  from display_service.skill_engine import region,region_matches
  raw=self.frame(60);box=[100,750,150,775];ref=region(raw,box)
  im=Image.open(io.BytesIO(raw));d=ImageDraw.Draw(im);d.rectangle((64,960,95,991),fill=(254,254,254));b=io.BytesIO();im.save(b,format='PNG');noise=b.getvalue()
  self.assertFalse(region_matches(ref,noise));self.assertTrue(quantized_core_matches(ref,noise))
  d.rectangle((70,965,75,970),fill=(100,100,100));b=io.BytesIO();im.save(b,format='PNG')
  self.assertFalse(quantized_core_matches(ref,b.getvalue()))
