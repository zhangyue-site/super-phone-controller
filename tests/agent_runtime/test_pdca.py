import io,unittest
from PIL import Image
from display_service.agent_pdca import Cycle,SourceUnverified
class Pdca(unittest.TestCase):
 def image(self,color):
  out=io.BytesIO();Image.new('RGB',(200,400),color).save(out,format='JPEG');return out.getvalue()
 def hint(self,labels):return dict(width=200,height=400,lines=[dict(text=t,bounds=[10,30+i*40,150,50+i*40])for i,t in enumerate(labels)])
 def test_wrong_app_vip_date_cannot_verify_requested_app(self):
  cycle=Cycle('优酷视频');cycle.observe(self.image('white'),self.hint(['星钻VIP会员','有效期2030.03.14','使用中','我知道了']))
  with self.assertRaises(SourceUnverified):cycle.require_source()
  self.assertFalse(cycle.source_verified)
 def test_ack_alone_is_not_app_identity(self):
  cycle=Cycle('优酷视频');before=self.hint(['优酷视频','腾讯视频','爱奇艺','芒果TV'])
  cycle.plan(dict(capability='open_app',target='优酷视频'),self.image('white'),before,[10,30,150,50]);cycle.receipt('confirmed');cycle.observe(self.image('white'),before)
  self.assertFalse(cycle.source_verified)
 def test_confirmed_named_entry_plus_changed_new_page_is_provenance(self):
  cycle=Cycle('优酷视频');cycle.plan(dict(capability='open_app',target='优酷视频'),self.image('white'),self.hint(['优酷视频']),[10,30,150,50]);cycle.receipt('confirmed')
  cycle.observe(self.image('black'),self.hint(['首页','短剧','会员','我的']))
  cycle.require_source();self.assertEqual(cycle.source_basis,'confirmed_named_entry')
 def test_entry_into_another_app_does_not_verify_expected_app(self):
  cycle=Cycle('优酷视频');cycle.plan(dict(capability='open_app',target='爱奇艺'),self.image('white'),self.hint(['爱奇艺']));cycle.receipt('confirmed');cycle.observe(self.image('black'),self.hint(['首页','短剧','会员','我的']))
  self.assertFalse(cycle.source_verified)
 def test_model_success_with_unchanged_frame_is_not_effect_success(self):
  cycle=Cycle();raw=self.image('white');hint=self.hint(['当前页'])
  for repeat in [1,2]:
   cycle.plan(dict(capability='tap_text',target='我的'),raw,hint);cycle.receipt('confirmed');check=cycle.check(raw,hint,dict(step_verified=True,done=True));self.assertFalse(check['effect_verified']);self.assertEqual(check['repeat'],repeat)
  self.assertTrue(check['stop'])
 def test_unknown_receipt_is_not_replayed_or_verified(self):
  cycle=Cycle('优酷');cycle.plan(dict(capability='open_app',target='优酷'),self.image('white'),self.hint(['优酷']));cycle.receipt('unknown');check=cycle.check(self.image('black'),self.hint(['首页','会员','我的','短剧']),dict(done=True));self.assertFalse(check['effect_verified']);self.assertFalse(check['retry_input']);self.assertFalse(cycle.source_verified)
 def test_home_invalidates_source(self):
  cycle=Cycle('优酷视频');cycle.plan(dict(capability='open_app',target='优酷视频'),self.image('white'),self.hint(['优酷视频']),[10,30,150,50]);cycle.receipt('confirmed');cycle.observe(self.image('black'),self.hint(['首页','短剧','会员','我的']));self.assertTrue(cycle.source_verified);cycle.plan(dict(capability='home',target='回桌面'),self.image('white'),self.hint(['优酷视频']));self.assertFalse(cycle.source_verified)
 def test_source_failures_are_bounded(self):
  cycle=Cycle('目标应用')
  for i in range(3):
   with self.assertRaises(SourceUnverified)as error:cycle.require_source()
   self.assertEqual(error.exception.terminal,i==2)
if __name__=='__main__':unittest.main()
