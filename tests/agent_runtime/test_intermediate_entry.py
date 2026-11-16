import io,unittest
from PIL import Image
from display_service.agent_pdca import Cycle
class Entry(unittest.TestCase):
 def image(self,color):
  out=io.BytesIO();Image.new('RGB',(300,600),color).save(out,format='JPEG');return out.getvalue()
 def hint(self,labels):return dict(width=300,height=600,lines=[dict(text=t,bounds=[10+(i%3)*100,120+(i//3)*180,80+(i%3)*100,140+(i//3)*180])for i,t in enumerate(labels)])
 def test_open_app_transition_is_not_whole_goal_success(self):
  cycle=Cycle();cycle.plan(dict(capability='open_app',target='浏览器'),self.image('white'),self.hint(['浏览器','其他应用']),[10,120,80,140]);cycle.receipt('confirmed');goal=dict(done=False)
  check=cycle.check(self.image('black'),self.hint(['搜索','标签','导航','新闻']),goal);self.assertTrue(check['effect_verified']);self.assertEqual(check['effect_basis'],'application_surface_changed');self.assertFalse(goal['done'])
 def test_home_to_grid_is_independent_step_success(self):
  cycle=Cycle();cycle.plan(dict(capability='home',target='回桌面'),self.image('white'),self.hint(['当前应用']));cycle.receipt('confirmed');check=cycle.check(self.image('black'),self.hint(['甲','乙','丙','丁','戊','己']),dict(done=False));self.assertTrue(check['effect_verified']);self.assertEqual(check['effect_basis'],'launcher_grid_after_home')
if __name__=='__main__':unittest.main()
