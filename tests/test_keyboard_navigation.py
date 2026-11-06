import unittest
from display_service.keyboard_navigation import decision
class KeyboardNavigation(unittest.TestCase):
 def focus(self,**kw):return dict(input_visible=True,input_focused=True,input_role='search',input_password=False,safe=True,**kw)
 def test_ascii_uses_usb_not_adb(self):
  c,s,w=decision(None,self.focus(action='type_text',text='wifi'),'搜索wifi',2)
  self.assertEqual(c['op'],'hid_text');self.assertEqual(c['text'],'wifi');self.assertFalse(w)
  c,s,w=decision(s,self.focus(committed_text='wifi'),'搜索wifi',3)
  self.assertTrue(w);self.assertTrue(s['verified'])
  with self.assertRaises(ValueError):decision(s,self.focus(action='type_text',text='wifi'),'搜索wifi',4)
 def test_phrase_candidate_requires_post_click_verification(self):
  c,s,_=decision(None,self.focus(action='type_text',text='北京'),'搜索北京',2)
  self.assertEqual(c['text'],'beijing')
  c,s,w=decision(s,self.focus(candidates=[dict(text='背景',bounds=[1,1,2,2]),dict(text='北京',bounds=[10,100,200,200])]),'搜索北京',3)
  self.assertEqual(c['op'],'hid_pointer');self.assertFalse(s['verified'])
  with self.assertRaises(ValueError):decision(s,self.focus(committed_text='背景'),'搜索北京',4)
  c,s,w=decision(s,self.focus(committed_text='北京'),'搜索北京',4)
  self.assertTrue(s['verified']);self.assertTrue(w)
 def test_unfocused_password_and_other_text_rejected(self):
  for change in ({'input_focused':False},{'input_password':True},{'input_role':'message'},{'text':'其他'}):
   o=self.focus(action='type_text',text='北京');o.update(change)
   with self.assertRaises(ValueError):decision(None,o,'搜索北京',1)
 def test_stale_candidate_and_unknown_rejected(self):
  _,s,_=decision(None,self.focus(action='type_text',text='北京'),'搜索北京',2)
  for frame,candidates in [(2,[dict(text='北京',bounds=[1,1,2,2])]),(3,[])]:
   with self.assertRaises(ValueError):decision(s,self.focus(candidates=candidates),'搜索北京',frame)
if __name__=='__main__':unittest.main()
