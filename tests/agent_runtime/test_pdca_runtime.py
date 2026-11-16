import unittest,tempfile,io,copy
from PIL import Image
from types import SimpleNamespace as N
from unittest.mock import Mock,patch
from display_service import agent_runtime as r
from display_service.agent_contract import Authority
from display_service.skill_engine import signature
class PdcaRuntime(unittest.TestCase):
 def test_false_success_in_wrong_app_never_finishes_or_issues_input(self):
  out=io.BytesIO();Image.new('RGB',(200,400),'white').save(out,format='JPEG');raw=out.getvalue();seq=[0];t=[1.]
  def clock():t[0]+=.001;return t[0]
  def fresh(*a,**kw):seq[0]+=1;return raw,seq[0],signature(raw),dict(width=200,height=400,source='phone-ocr',lines=[dict(text='星钻VIP会员',bounds=[10,50,150,70]),dict(text='2030.03.14',bounds=[10,90,150,110])])
  info=dict(goal='读取优酷视频会员到期日期',scope=dict(source_app='优酷视频'),stages=[dict(id='read',goal='读取',success='日期')],completion=['优酷会员日期'],questions=[],assumptions=[],capabilities=['read_record','observe','verify'],original='请查询优酷视频会员到期日期')
  auth=Authority('t','d','s','lease',frozenset(info['capabilities']),999.);action=Mock(side_effect=AssertionError('no input authorized for a fabricated success'));calls=[]
  def plan(*a,**kw):calls.append(1);return dict(safe=True,done=True,evidence='优酷星钻会员2030.03.14',step=None)
  with tempfile.TemporaryDirectory()as tmp,patch.object(r,'fresh',side_effect=fresh):
   result=r.run(N(m=N(_live=lambda j:None),_action=action),N(device='d',screen_session='s'),info['original'],authority=auth,guard=lambda a:True,policy=lambda *a:True,intake=lambda t:info,planner=plan,clock=clock,record_scope=dict(mode='read_only',source_app='优酷视频',target_app=None,start=None,end=None,allow_save=False,journal_path=tmp+'/j.db'))
  self.assertFalse(result['verified']);self.assertEqual(result['failure']['code'],'source_identity_unknown');self.assertLessEqual(len(calls),3);action.assert_not_called();self.assertFalse(result['progress'])
if __name__=='__main__':unittest.main()
