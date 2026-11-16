import copy,io,unittest
from PIL import Image,ImageDraw
from display_service.agent_contract import Authority
from display_service.agent_observation import capture,bind_visual
from display_service.agent_gesture_observation import geometry,rebind_gesture,checked_container
from display_service.agent_gates import GateError
from display_service.agent_runtime import _locate
STEP=dict(capability="page",target="内容区域",locator="region",bounds=[10,40,190,360],direction="up",end=None)
AUTH=Authority("task","device","session","lease",frozenset({"page","observe"}),999)
LINES=[dict(text="甲锚点",bounds=[20,60,60,80]),dict(text="乙锚点",bounds=[130,60,170,80]),dict(text="丙锚点",bounds=[20,320,60,340])]
def raw(change=None):
 im=Image.new('RGB',(200,400),'white')
 if change:ImageDraw.Draw(im).rectangle(change,fill='red')
 out=io.BytesIO();im.save(out,format='PNG');return out.getvalue()
def shot(seq,data,lines=LINES,auth=AUTH):return capture(auth,seq,data,dict(width=200,height=400,lines=lines),observed_at=1.)
def view(s):return bind_visual(s,dict(scene='generic content',widgets=[],regions=[dict(role='scroll_container',bounds=STEP['bounds'])]))
class Gestures(unittest.TestCase):
 def setUp(self):self.a=raw();self.old=shot(1,self.a);self.v=view(self.old);self.cmd,self.origin=_locate(STEP,self.old.hint(),(),self.v)
 def bind(self,data,lines=LINES,auth=AUTH,cmd=None):return rebind_gesture(self.v,self.old,shot(2,data,lines,auth),self.a,data,STEP,cmd or self.cmd)
 def test_actual_hid_origin_matches(self):
  origin,path,c=geometry(STEP,self.old.hint());self.assertEqual(origin,self.origin);self.assertEqual(c,self.cmd);self.assertNotEqual(origin,STEP['bounds'])
 def test_dynamic_container_outside_path_allowed(self):
  data=raw([20,180,40,220]);self.assertEqual(self.bind(data)['observation'],shot(2,data).identity())
 def test_changed_origin_rejected(self):
  with self.assertRaises(GateError):self.bind(raw([99,295,101,297]))
 def test_path_overlay_rejected(self):
  with self.assertRaises(GateError):self.bind(raw([95,180,105,205]))
 def test_new_permission_ocr_rejected(self):
  with self.assertRaises(GateError):self.bind(self.a,LINES+[dict(text='是否允许访问',bounds=[80,180,130,200])])
 def test_page_identity_changed_rejected(self):
  with self.assertRaises(GateError):self.bind(self.a,[dict(r,text='new'+str(i)) for i,r in enumerate(LINES)])
 def test_scope_rejected(self):
  with self.assertRaises(GateError):self.bind(self.a,auth=Authority('task','device','other','lease',frozenset({'page'}),999))
 def test_hid_endpoint_changed_rejected(self):
  with self.assertRaises(GateError):self.bind(self.a,cmd=dict(self.cmd,y2=self.cmd['y2']+1))
 def test_distributed_anchors_required(self):
  with self.assertRaises(GateError):self.bind(self.a,LINES[:2])
 def test_control_at_origin_rejected(self):
  self.v['widgets']=[dict(role='app_icon',label='app',bounds=self.origin)]
  with self.assertRaises(GateError):self.bind(self.a)
 def test_container_role_required(self):
  self.v['regions'][0]['role']='navigation'
  with self.assertRaises(GateError):self.bind(self.a)
 def test_final_frame_rebind_repeats_path_checks(self):
  b=raw([20,180,40,220]);mid=shot(2,b);v=rebind_gesture(self.v,self.old,mid,self.a,b,STEP,self.cmd)
  c=raw([95,180,105,205])
  with self.assertRaises(GateError):rebind_gesture(v,mid,shot(3,c),b,c,STEP,self.cmd)
if __name__=='__main__':unittest.main()
