import unittest,copy,io
from types import SimpleNamespace as N
from unittest.mock import patch,Mock
from PIL import Image
from display_service import agent_runtime as r
from display_service.agent_contract import Authority
from display_service.skill_engine import signature
class Feedback(unittest.TestCase):
 def test_confirmed_new_action_retires_old_location_failure(self):
  out=io.BytesIO();Image.new('RGB',(200,400),'white').save(out,format='JPEG');raw=out.getvalue();sig=signature(raw);seq=[0];now=[1.];checked=[]
  changed=io.BytesIO();Image.new('RGB',(200,400),'black').save(changed,format='JPEG');after_raw=changed.getvalue()
  def clock():now[0]+=.001;return now[0]
  def fresh(*a,**kw):
   seq[0]+=1;current=after_raw if action.called else raw
   return current,seq[0],signature(current),dict(width=200,height=400,source='phone-ocr',lines=[dict(text='优酷首页' if action.called else '优酷视频',bounds=[10,30,90,50])])
  info=dict(goal='打开优酷视频',scope={},stages=[dict(id='open',goal='打开',success='首页')],completion=['首页'],questions=[],assumptions=[],capabilities=['observe','open_app','verify'],original='打开优酷视频',_feedback=[dict(code='frame_changed',input_sent=False,reason='旧帧改变')])
  auth=Authority('t','d','s','lease',frozenset(info['capabilities']),999.);action=Mock(return_value={'ok':True})
  def plan(raw,hint,info,**kw):
   if kw.get('verify'):
    checked.append(True);self.assertEqual(info.get('_feedback'),[]);self.assertEqual(info['_last_action']['receipt'],'confirmed');return dict(safe=True,done=True,evidence='新画面已打开优酷',step=None)
   return dict(safe=True,done=False,evidence='当前可见优酷',step=dict(capability='open_app',target='优酷视频',locator='text',bounds=None))
  with patch.object(r,'fresh',side_effect=fresh):result=r.run(N(m=N(_live=lambda j:None),_action=action,_receipt_frame_floor=lambda j,s:s),N(device='d',screen_session='s'),info['original'],authority=auth,guard=lambda a:True,policy=lambda *a:True,intake=lambda t:info,planner=plan,clock=clock)
  self.assertTrue(checked);self.assertTrue(result['verified'],result['reply']);action.assert_called_once()
if __name__=='__main__':unittest.main()
