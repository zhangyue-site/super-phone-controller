import copy,json,unittest,math,io,os
from pathlib import Path
from unittest.mock import patch
from display_service import jev_vision,general_vision
from test_wechat_nav import frame
from PIL import Image,ImageDraw
def c(selected,keys):
 return dict(type='choice',choice=selected,confidence=1.,probabilities={k:float(k==selected) for k in keys})
def fixture(page='drawer',step='tap_settings'):
 return {'answers':{'page':c(page,('launcher','drawer','settings','other')),'next_step':c(step,('open_drawer','tap_settings','done','stop')),'settings_visible':c('yes',('yes','no','unknown')),'swipe_region_clear':c('yes',('yes','no','unknown')),'goal_reached':c('yes',('yes','no','unknown')),'settings_box':dict(type='box',confidence=.94,box=dict(left=.25,top=.59,right=.38,bottom=.67))}}
class JevTests(unittest.TestCase):
 def test_visible_settings_maps_fraction_box(self):
  o=jev_vision.observation(fixture(),'打开设置');self.assertEqual(o['bounds'],[250,590,380,670]);self.assertIsNone(o['confidence']);self.assertEqual(o['action'],'click')
 def test_drawer_requires_clear_region_and_no_settings(self):
  f=fixture('launcher','open_drawer');f['answers']['settings_visible']['choice']='no'
  self.assertEqual(jev_vision.observation(f,'打开设置',region_clear=True)['action'],'drag')
  with self.assertRaises(ValueError):jev_vision.observation(f,'打开设置',region_clear=False)
 def test_conflicting_page_and_action_rejected(self):
  with self.assertRaises(ValueError):jev_vision.observation(fixture('settings','tap_settings'),'打开设置')
  with self.assertRaises(ValueError):jev_vision.observation(fixture('launcher','open_drawer'),'打开设置')
 def test_low_confidence_outside_and_nan_box_never_click(self):
  for field,value in [('left',-.01),('right',1.01),('top',float('nan')),('bottom',.58)]:
   f=fixture()
   if field=='confidence':f['answers']['settings_box'][field]=value
   else:f['answers']['settings_box']['box'][field]=value
   with self.subTest(field=field),self.assertRaises(ValueError):jev_vision.observation(f,'打开设置')
 def test_completion_requires_independent_page_and_goal(self):
  f=fixture('settings','done');self.assertTrue(jev_vision.observation(f,'打开设置')['complete'])
  f['answers']['goal_reached']['choice']='unknown'
  with self.assertRaises(ValueError):jev_vision.observation(f,'打开设置')
 def test_other_application_and_verify_never_request_jev(self):
  with patch('urllib.request.OpenerDirector.open') as net:
   with self.assertRaises(ValueError):jev_vision.observe(b'','打开相机')
   with self.assertRaises(ValueError):jev_vision.observe(b'','打开设置',True)
   net.assert_not_called()
 def test_general_router_uses_jev_only_for_nonverify_settings(self):
  with patch.dict(os.environ,{'EPAPER_NAV_JUDGE':'jev'}),patch.object(jev_vision,'clear_swipe_region',return_value=True),patch.object(jev_vision,'observe',return_value={'complete':False}) as judge,patch('display_service.general_vision._open_vision') as net:
   self.assertEqual(general_vision.observe(frame(0),'打开设置'),{'complete':False});judge.assert_called_once();net.assert_not_called()
   judge.reset_mock()
   response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'coordinate_system':'pixels','confidence':1,'complete':True})}}]}
   net.return_value=io.BytesIO(json.dumps(response).encode())
   with patch.object(general_vision,'vision_route',return_value=('opencode-go','mimo-v2.6-flash',{'baseUrl':'https://models.invalid/v1','apiKey':'synthetic-only'})):
    general_vision.observe(frame(0),'打开设置',True)
   judge.assert_not_called();self.assertEqual(net.call_count,1)

 def test_wallpaper_patch_and_visible_control_edges(self):
  im=Image.new('RGB',(640,1280),(180,140,160));b=io.BytesIO();im.save(b,format='JPEG')
  self.assertTrue(jev_vision.clear_swipe_region(b.getvalue()))
  ImageDraw.Draw(im).rectangle((290,800,350,855),fill='black');b=io.BytesIO();im.save(b,format='JPEG')
  self.assertFalse(jev_vision.clear_swipe_region(b.getvalue()))

 def test_nonblank_page_uses_general_locator_without_jev(self):
  response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'coordinate_system':'pixels','confidence':.97,'bounds':[20,30,80,100],'safe':True,'action':'click','target_label':'设置'})}}]}
  route=('xiaomi','mimo-v2.6-flash',{'baseUrl':'https://models.invalid/v1','apiKey':'synthetic-only'})
  with patch.dict(os.environ,{'EPAPER_NAV_JUDGE':'jev'}),patch.object(jev_vision,'clear_swipe_region',return_value=False),patch.object(jev_vision,'observe') as judge,patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(response).encode())) as net,patch.object(general_vision,'vision_route',return_value=route):
   result=general_vision.observe(frame(0),'打开设置');self.assertEqual(result['confidence'],.97);net.assert_called_once();judge.assert_not_called()

 def test_unconfirmed_visible_settings_never_authorizes_click(self):
  for selected in ('no','unknown'):
   f=fixture('launcher','tap_settings');f['answers']['settings_visible']['choice']=selected
   with self.assertRaises(ValueError):jev_vision.observation(f,'打开设置')
  f=fixture();f['answers']['settings_box']['confidence']=0
  self.assertEqual(jev_vision.observation(f,'打开设置')['action'],'click')
 def test_independent_locator_only_accepts_visible_settings(self):
  route=('xiaomi','mimo-v2.6-flash',{'baseUrl':'https://models.invalid/v1','apiKey':'synthetic-only'})
  for label,okay in [('设置',True),('Minis',False)]:
   response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(dict(coordinate_system='pixels',confidence=.97,safe=True,screen='安卓桌面',action='click',target_label=label,bounds=[20,30,80,100]))}}]}
   with self.subTest(label=label),patch.dict(os.environ,{'EPAPER_NAV_JUDGE':'jev'}),patch.object(jev_vision,'clear_swipe_region',return_value=True),patch.object(jev_vision,'observe',side_effect=jev_vision.SettingsEntryUncertain('launcher')),patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(response).encode())),patch.object(general_vision,'vision_route',return_value=route):
    if okay:self.assertTrue(general_vision.observe(frame(0),'打开设置')['_trusted_launcher_settings'])
    else:
     with self.assertRaises(ValueError):general_vision.observe(frame(0),'打开设置')
 def test_other_judge_errors_never_use_independent_locator(self):
  with patch.dict(os.environ,{'EPAPER_NAV_JUDGE':'jev'}),patch.object(jev_vision,'clear_swipe_region',return_value=True),patch.object(jev_vision,'observe',side_effect=ValueError('unsafe')),patch('display_service.general_vision._open_vision') as net:
   with self.assertRaises(ValueError):general_vision.observe(frame(0),'打开设置')
   net.assert_not_called()
