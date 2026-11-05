
import importlib.util,io,json,os,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from display_service import relay_http as live

candidate=live
class Handler:
 command='POST'
 def __init__(self,op):
  self.path='/app-relay/'+op
  obj={'nonce':'0'*32}
  if op=='maintenance':obj['op']=12
  if op=='ack':obj.update(id='a'*32,receipt={})
  raw=json.dumps(obj).encode();self.rfile=io.BytesIO(raw)
  self.headers={'Authorization':'Bearer '+'t'*43,'Content-Length':str(len(raw))}
 def reply(self,status,body):self.result=(status,json.loads(body))
class ExpiryTests(unittest.TestCase):
 def run_request(self,op,reason,authenticated=True):
  h=Handler(op);g=SimpleNamespace()
  def fail(*args):raise PermissionError(reason)
  setattr(g,op,fail)
  owner=SimpleNamespace(return_value=('android-app','owner','owner','test-board'))
  with patch.dict(os.environ,EPAPER_RELAY_CONTROL='1'),patch.object(candidate.app_control,'owner',return_value=owner.return_value,side_effect=None if authenticated else PermissionError(reason)),patch.object(candidate,'gateway',return_value=g):
   self.assertTrue(candidate.handle(h,Path('/unused')))
  return h.result
 def test_only_authenticated_poll_and_maintenance_timeout_are_recoverable(self):
  for op in ('poll','maintenance'):
   status,body=self.run_request(op,'relay expired; reconcile first')
   self.assertEqual(status,409);self.assertEqual(body['code'],'relay_lease_expired')
 def test_auth_owner_nonce_and_pending_ack_remain_terminal(self):
  for op,reason in (('poll','ticket'),('poll','relay owner'),('poll','gateway lease'),('ack','relay expired; reconcile first')):
   status,body=self.run_request(op,reason)
   self.assertEqual(status,403);self.assertNotIn('code',body)
 def test_unauthenticated_error_cannot_claim_recovery(self):
  status,body=self.run_request('poll','relay expired; reconcile first',False)
  self.assertEqual(status,403);self.assertNotIn('code',body)
if __name__=='__main__':unittest.main()
