from test_gesture_observation import *
class BlankContext(unittest.TestCase):
 def test_blank_uses_page_anchors_but_scroll_does_not(self):
  step=dict(STEP,bounds=[10,110,190,280],direction='left')
  data=raw();old=shot(1,data);new=shot(2,data)
  for role in ('blank_gesture_area','scroll_container'):
   v=bind_visual(old,dict(scene='launcher',widgets=[],regions=[dict(role=role,bounds=step['bounds'])]))
   cmd=geometry(step,old.hint())[2]
   if role=='blank_gesture_area':self.assertEqual(rebind_gesture(v,old,new,data,data,step,cmd)['observation'],new.identity())
   else:
    with self.assertRaises(GateError):rebind_gesture(v,old,new,data,data,step,cmd)
 def test_blank_still_rejects_page_change(self):
  step=dict(STEP,bounds=[10,110,190,280],direction='left');data=raw();old=shot(1,data)
  v=bind_visual(old,dict(scene='launcher',widgets=[],regions=[dict(role='blank_gesture_area',bounds=step['bounds'])]))
  cmd=geometry(step,old.hint())[2]
  with self.assertRaises(GateError):rebind_gesture(v,old,shot(2,data,LINES[:2]),data,data,step,cmd)
