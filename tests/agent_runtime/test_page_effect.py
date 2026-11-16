import unittest,io,copy
from PIL import Image
from display_service.agent_pdca import Cycle
class PageEffect(unittest.TestCase):
 def image(self,color):
  out=io.BytesIO();Image.new('RGB',(200,400),color).save(out,format='JPEG');return out.getvalue()
 def hint(self,names,shift=0):return dict(width=200,height=400,lines=[dict(text=t,bounds=[10+(i%2)*100,80+(i//2)*100+shift,90+(i%2)*100,100+(i//2)*100+shift])for i,t in enumerate(names)])
 def test_intermediate_page_change_is_success_even_when_goal_not_finished(self):
  cycle=Cycle();before=self.hint(['百度网盘','实用工具','相册','主题']);after=self.hint(['BOOX助手','居家生活','小红书','地图'])
  cycle.plan(dict(capability='page',target='桌面应用列表',direction='left'),self.image('white'),before,[0,50,200,350]);cycle.receipt('confirmed')
  goal_result=dict(safe=True,done=False,step=None,evidence='尚未找到设置')
  check=cycle.check(self.image('black'),after,goal_result)
  self.assertTrue(check['effect_verified']);self.assertEqual(check['effect_basis'],'container_content_replaced');self.assertFalse(goal_result['done'])
 def test_background_animation_without_content_change_is_not_scroll_success(self):
  cycle=Cycle();hint=self.hint(['百度网盘','实用工具','相册','主题']);cycle.plan(dict(capability='page',target='桌面应用列表',direction='left'),self.image('white'),hint,[0,50,200,350]);cycle.receipt('confirmed');check=cycle.check(self.image('black'),hint,dict(done=False))
  self.assertFalse(check['effect_verified'])
 def test_ocr_jitter_is_not_a_scroll(self):
  cycle=Cycle();before=self.hint(['甲','乙','丙','丁']);after=self.hint(['甲','乙','丙','丁'],shift=1);cycle.plan(dict(capability='page',target='列表',direction='up'),self.image('white'),before,[0,50,200,350]);cycle.receipt('confirmed');self.assertFalse(cycle.check(self.image('black'),after,dict(done=False))['effect_verified'])
 def test_directional_label_motion_is_independent_step_evidence(self):
  cycle=Cycle();before=self.hint(['甲','乙','丙','丁']);after=self.hint(['甲','乙','丙','丁'],shift=-30);cycle.plan(dict(capability='page',target='列表',direction='up'),self.image('white'),before,[0,50,200,350]);cycle.receipt('confirmed');self.assertTrue(cycle.check(self.image('black'),after,dict(done=False))['effect_verified'])
if __name__=='__main__':unittest.main()
