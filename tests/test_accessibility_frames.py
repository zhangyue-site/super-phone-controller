import base64, copy, hashlib, io, json, unittest
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from display_service import app_screen, accessibility
from display_service.app_ota import Authority
from display_service.dialogue import Mailbox

def jpeg():
 out=io.BytesIO();Image.new('RGB',(240,480),'white').save(out,'JPEG');return out.getvalue()
def tree():
 return dict(version=1,width=1080,height=2160,ageMs=20,stableForMs=300,package='com.miui.home',nodes=[dict(text='支付宝',description='',bounds=[100,200,300,400],clickable=True,editable=False)])
class Handler:
 command='POST';path='/app-screen/frame'
 def reply(self,status,body,kind=None):self.status=status;self.value=json.loads(body)
class Tests(unittest.TestCase):
 def setUp(self):
  self.m=Mailbox();self.j=self.m.create('board','a'*16,1);self.j.fenced=True;self.ticket='t'*43;self.j.screen_session=self.ticket
  self.auth=Authority();self.auth.tickets[self.ticket]=(self.auth.clock()+300,'board','screen')
  self.patches=[patch.object(app_screen,'AUTHORITY',self.auth),patch.object(app_screen,'CONVERSATION',SimpleNamespace(mailbox=self.m)),patch.object(app_screen,'SEQUENCES',{})]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
 def request(self,snapshot=None,sequence=1,barrier=None,legacy=False):
  raw=jpeg() if legacy else json.dumps(dict(jpegBase64=base64.b64encode(jpeg()).decode(),accessibility=snapshot or tree())).encode()
  h=Handler();h.rfile=io.BytesIO(raw);h.headers={'Authorization':'Bearer '+self.ticket,'Content-Type':'image/jpeg' if legacy else accessibility.CONTENT_TYPE,'Content-Length':str(len(raw)),'X-Screen-Sequence':str(sequence),'X-Screen-Barrier':barrier or self.j.video_barrier,'X-Screen-Native-Width':'1080','X-Screen-Native-Height':'2160'}
  app_screen.handle(h,None);return h
 def test_legacy_jpeg_still_works(self):
  self.assertEqual(self.request(legacy=True).status,200)
  self.assertIsNone(accessibility.frame_hint(self.m,self.j,self.j.video))
 def test_frame_envelope_is_bound_to_exact_image_and_scaled(self):
  self.assertEqual(self.request().status,200)
  hint=accessibility.frame_hint(self.m,self.j,self.j.video)
  self.assertEqual(hint['nodes'][0]['bounds'],[22,44,67,89])
  self.assertEqual(hint['package'],'com.miui.home')
  self.assertIsNone(accessibility.frame_hint(self.m,self.j,b'different image'))
 def test_old_barrier_never_attaches_nodes(self):
  self.assertEqual(self.request(barrier='f'*32).status,202)
  self.assertFalse(getattr(self.j,'accessibility_frame',None))
 def test_rotation_and_stale_tree_fall_back_to_jpeg_without_nodes(self):
  for field,value in [('width',2160),('ageMs',501),('stableForMs',0),('nodes',[dict(tree()['nodes'][0],password=True)])]:
   snapshot=tree();snapshot[field]=value
   h=self.request(snapshot,sequence=self.j.video_sequence+1)
   self.assertEqual(h.status,200)
   self.assertIsNone(accessibility.frame_hint(self.m,self.j,self.j.video))
 def test_authorization_revoked_cannot_consume_metadata(self):
  self.request();self.auth.tickets.clear()
  self.assertIsNone(accessibility.frame_hint(self.m,self.j,self.j.video))
 def test_changed_scene_or_expired_frame_cannot_reuse_nodes(self):
  self.request();self.j.video_barrier='f'*32
  self.assertIsNone(accessibility.frame_hint(self.m,self.j,self.j.video))
 def test_fresh_legacy_frame_clears_old_nodes(self):
  self.request();self.assertEqual(self.request(sequence=2,legacy=True).status,200)
  self.assertIsNone(accessibility.frame_hint(self.m,self.j,self.j.video))
 def test_only_unique_explicit_launch_target_can_skip_model(self):
  hint=dict(tree(),nodes=[dict(tree()['nodes'][0],bounds=[100,100,200,150])],width=240,height=480)
  result=accessibility.navigation_hint(hint,'打开支付宝')
  self.assertEqual(result['target_label'],'支付宝')
  self.assertEqual(result['bounds'],[416,208,833,312])
  self.assertFalse(result['complete'])
  hint['nodes']*=2
  self.assertIsNone(accessibility.navigation_hint(hint,'打开支付宝'))
 def test_no_payment_save_or_unknown_task_fast_path(self):
  for task in ['打开支付宝然后付款','保存账单','打开微信发送消息','打开任意东西']:
   self.assertIsNone(accessibility.navigation_hint(tree(),task))
 def test_hidden_or_editable_nodes_cannot_be_targets(self):
  t=tree();t['nodes'][0]['editable']=True
  self.assertIsNone(accessibility.navigation_hint(t,'打开支付宝'))
 def test_tree_bounds_and_payload_limits(self):
  for change in [dict(nodes=tree()['nodes']*193),dict(nodes=[dict(tree()['nodes'][0],bounds=[-1,0,10,10])]),dict(package='bad\nname')]:
   self.assertIsNone(accessibility.validate_tree(dict(tree(),**change),1080,2160,240,480))
if __name__=='__main__':unittest.main()
