import unittest
from types import SimpleNamespace
from unittest.mock import patch
from display_service.wechat_nav import WechatNavigator
from display_service import jev_vision as jv, general_nav as gn, general_vision as gv, store_policy as sp

class ObservationPolicy(unittest.TestCase):
 def test_no_self_score_gate_or_required_score(self):
  mailbox=SimpleNamespace(lock=__import__('threading').RLock(),_live=lambda job:None)
  job=SimpleNamespace(video_barrier=1,screen_session='same')
  for score in (None,0,.7,.99):
   for verify in (False,True):
    value={'safe':True,'complete':verify,'verified':verify,'action':'click','bounds':[10,10,50,50]}
    if score is not None:value['confidence']=score
    nav=WechatNavigator(mailbox,object(),vision=lambda *a:value)
    nav._log=lambda *a,**k:None
    self.assertIs(nav._observe(job,b'frame','打开设置',verify),value)
 def test_changed_capture_still_rejected(self):
  mailbox=SimpleNamespace(lock=__import__('threading').RLock(),_live=lambda job:None)
  job=SimpleNamespace(video_barrier=1,screen_session='old')
  def vision(*args):job.screen_session='new';return {'safe':True}
  nav=WechatNavigator(mailbox,object(),vision=vision)
  with self.assertRaisesRegex(ValueError,'会话'):nav._observe(job,b'f','打开设置')
 def test_launcher_path_has_no_score_dependency(self):
  for score in (None,.1):
   v=dict(screen='安卓桌面',safe=True,complete=False,action='click',confidence=score)
   with patch.object(jv,'clear_swipe_region',return_value=True):
    self.assertTrue(gv.launcher_method(v,b'frame','打开计算器').get('_trusted_launcher_blank'))
 def test_reobserve_is_semantic(self):
  v=dict(screen='桌面',action='click',target_label='设置',safe=True,complete=False)
  self.assertTrue(gn._may_reobserve_settings('打开设置',v))
  v['safe']=False;self.assertFalse(gn._may_reobserve_settings('打开设置',v))
 def test_jev_choice_no_self_score_cutoff(self):
  for score in (.1,None):
   a={'type':'choice','choice':'launcher','confidence':score,'probabilities':{'launcher':.4,'other':.6}}
   self.assertEqual(jv.choice(a,('launcher','other'))[0],'launcher')
 def test_explicit_verdict_rejects_unknown(self):
  self.assertTrue(jv.verdict({'type':'choice','choice':'yes'}))
  self.assertFalse(jv.verdict({'type':'choice','choice':'no'}))
  self.assertFalse(jv.verdict({'type':'choice','choice':'unknown'}))
  with self.assertRaises(ValueError):jv.verdict({'type':'noul','noul':.99})
 def test_search_focus_does_not_require_score(self):
  o=dict(action='click',target_label='搜索框',bounds=[100,40,600,130])
  self.assertTrue(sp.is_search_focus(o));o['bounds']=[100,40,600,500];self.assertFalse(sp.is_search_focus(o))
 def test_unknown_action_and_bad_coordinates_still_rejected(self):
  nav=gn.GeneralNavigator(object(),object())
  for a,b in [('unknown',[10,10,20,20]),('click',[-1,10,20,20])]:
   with self.assertRaises(ValueError):nav._command(dict(action=a,bounds=b,target_label='设置',safe=True),'打开设置')

 def test_jev_categorical_navigation_and_unknown(self):
  def c(value):return {'type':'choice','choice':value,'confidence':.01}
  value={'answers':{'page':c('launcher'),'next_step':c('open_drawer'),'settings_visible':c('no')}}
  self.assertEqual(jv.observation(value,'打开设置',True)['action'],'drag')
  value['answers']['settings_visible']=c('unknown')
  with self.assertRaises(ValueError):jv.observation(value,'打开设置',True)
  value={'answers':{'page':c('settings'),'next_step':c('done'),'goal_reached':c('yes')}}
  self.assertTrue(jv.observation(value,'打开设置')['complete'])
  value['answers']['goal_reached']=c('unknown')
  with self.assertRaises(ValueError):jv.observation(value,'打开设置')
 def test_final_verification_requires_visible_evidence(self):
  nav=gn.GeneralNavigator(object(),object())
  good=dict(complete=True,verified=True,task='打开设置',safe=True,evidence='可见设置标题和网络、电池列表',application='设置')
  nav._validate_final(good,'打开设置')
  for key,value in [('verified',False),('safe',False),('evidence',''),('application','桌面')]:
   with self.assertRaises(ValueError):nav._validate_final(dict(good,**{key:value}),'打开设置')

if __name__=='__main__':unittest.main()
