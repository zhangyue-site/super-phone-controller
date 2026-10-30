"""Predispatch rejection is not a sent HID action or permission to replay one."""
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from display_service.general_nav import GeneralNavigator
from display_service.dialogue import Mailbox
from display_service.skill_engine import SkillStore,signature
from display_service.wechat_nav import ActionFrameChanged
import io
from PIL import Image,ImageDraw
def frame(stage):
 im=Image.new('RGB',(240,480),['#16202b','#e4e4e4','#fff8e0','#e2ffee'][stage]);ImageDraw.Draw(im).rectangle((20+stage*12,100,90,165),fill=['green','black','red','blue'][stage])
 out=io.BytesIO();im.save(out,format='JPEG');return out.getvalue()
class BudgetTests(unittest.TestCase):
 def flow(self,reject=(2,4),cancel=False):
  m=Mailbox();j=m.create('synthetic','a'*16,1);j.pointer_protocol='absolute-v1';j.video_source='user-consented-app-screen'
  stage=0;checks=0;sequence=0;dispatch=[];observed=[]
  def vision(raw,task,verify=False):
   observed.append(stage);base=dict(safe=True,complete=False,target_label='搜索框',bounds=[100,100,300,200],input_visible=True,input_focused=True,input_password=False,input_role='search')
   if verify or stage>=3:return dict(base,complete=True,verified=True,task=task,application='设置',query='北京',committed_text='北京',evidence='设置搜索结果显示北京')
   if stage==0:return dict(base,action='click')
   if stage==1:return dict(base,action='type_text',text='北京')
   return dict(base,action='click',committed_text='',candidates=[dict(text='北京',bounds=[100,500,300,600])])
  def fresh(job,after=0):
   nonlocal sequence
   sequence=max(sequence,after)+1;job.video_sequence=sequence;raw=frame(stage)
   return raw,sequence,signature(raw)
  def check(*_):
   nonlocal checks
   checks+=1
   if checks in reject:
    if cancel:m.cancel(j.device)
    return False
   return True
  def execute(job,command):
   nonlocal stage
   op=command['op'];dispatch.append(op)
   if op=='hid_text':stage=2
   elif op=='hid_pointer':stage=1 if stage==0 else 3
   job.last_receipt=dict(id=f'{len(dispatch):032x}',op=op,ok=True)
   return {'hid_home':'HID_HOME_REPORT_SENT','hid_pointer':'HID_POINTER_REPORT_SENT','hid_text':'HID_TEXT_REPORT_SENT'}[op]
  with tempfile.TemporaryDirectory() as tmp:
   nav=GeneralNavigator(m,SkillStore(Path(tmp)),vision=vision,frame_timeout=.1)
   with patch.object(nav,'_frame',side_effect=fresh),patch.object(nav,'_matches_action_frame',side_effect=check),patch.object(m,'execute',side_effect=execute):
    if reject==(2,3) or cancel:
     with self.assertRaises(ValueError):nav.run(j,'打开设置搜索北京')
    else:self.assertIn('已通过',nav.run(j,'打开设置搜索北京'))
  return dispatch,observed
 def test_later_typing_gets_its_own_predispatch_reobservation_after_click_ack(self):
  sent,seen=self.flow();self.assertEqual(sent,['hid_home','hid_pointer','hid_text','hid_pointer']);self.assertEqual(seen.count(1),2)
 def test_candidate_rejection_never_retypes_acknowledged_pinyin(self):
  sent,_=self.flow(reject=(2,4,6));self.assertEqual(sent.count('hid_text'),1);self.assertEqual(sent,['hid_home','hid_pointer','hid_text','hid_pointer'])
 def test_consecutive_rejections_of_same_action_stop(self):self.assertEqual(self.flow(reject=(2,3))[0],['hid_home'])
 def test_stop_after_predispatch_rejection_prevents_more_model_reads(self):
  sent,seen=self.flow(cancel=True);self.assertEqual(sent,['hid_home']);self.assertEqual(seen,[0])
if __name__=='__main__':unittest.main()
