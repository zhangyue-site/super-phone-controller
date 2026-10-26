import io,unittest
from PIL import Image,ImageDraw
from display_service.store_policy import same_controls

def frame(offset=0,move=0,removed=False,popup=False):
 im=Image.new('RGB',(640,1280));p=im.load()
 for y in range(1280):
  for x in range(640):p[x,y]=(120+x//16+offset,90+y//32+offset,145+x//32+offset)
 d=ImageDraw.Draw(im)
 if not removed:
  d.ellipse((400+move,425,480+move,505),fill='white');d.rectangle((420+move,445,460+move,485),fill=(0,130,100));d.text((415+move,527),'APP STORE',fill='white')
 if popup:d.rectangle((50,200,590,950),fill='white');d.text((100,300),'INSTALL OTHER APP?',fill='black')
 out=io.BytesIO();im.save(out,format='JPEG',quality=85);return out.getvalue()
class StoreFramesTests(unittest.TestCase):
 def test_small_background_luminance_change_keeps_identical_controls(self):self.assertTrue(same_controls(frame(),frame(offset=2),[623,332,750,394]))
 def test_removed_moved_control_popup_and_large_brightness_change_fail(self):
  for changed in (frame(move=2),frame(move=8),frame(removed=True),frame(popup=True),frame(offset=20)):
   with self.subTest(changed=len(changed)):self.assertFalse(same_controls(frame(),changed,[623,332,750,394]))

 def test_changed_page_never_offers_pointer(self):
  from types import SimpleNamespace
  from unittest.mock import Mock
  from display_service.store_policy import pointer_action
  from display_service.skill_engine import signature
  current=frame(popup=True);execute=Mock();nav=SimpleNamespace(m=SimpleNamespace(_live=Mock(),execute=execute),_frame=Mock(return_value=(current,1,signature(current))),_log=Mock())
  with self.assertRaises(ValueError):pointer_action(nav,SimpleNamespace(),{'op':'hid_pointer'},frame(),[623,332,750,394])
  execute.assert_not_called()
 def test_pointer_requires_real_report_receipt(self):
  from types import SimpleNamespace
  from unittest.mock import Mock
  from display_service.store_policy import pointer_action
  from display_service.skill_engine import signature
  raw=frame();execute=Mock(return_value='queued');nav=SimpleNamespace(m=SimpleNamespace(_live=Mock(),execute=execute),_frame=Mock(return_value=(raw,1,signature(raw))),_log=Mock())
  with self.assertRaises(ValueError):pointer_action(nav,SimpleNamespace(last_receipt={}),{'op':'hid_pointer'},raw,[623,332,750,394])
  self.assertEqual(execute.call_count,1)
