import hashlib,hmac,io,json,tempfile,threading,unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from display_service import app_control as c,app_screen
from display_service.app_ota import Authority
from display_service.paired_control import Pairings

class Handler:
 command='POST'
 def __init__(self,path,obj,ticket=None):
  self.path='/app-control/'+path;raw=json.dumps(obj).encode();self.rfile=io.BytesIO(raw)
  self.headers={'Content-Length':str(len(raw))}
  if ticket:self.headers['Authorization']='Bearer '+ticket
 def reply(self,code,data,*args):self.code=code;self.data=json.loads(data)

class USBControlTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.config=Path(self.tmp.name)/'keys';self.config.write_text(json.dumps({'board':'secret','other':'other-secret'}))
  self.now=100.;self.auth=Authority(clock=lambda:self.now,firmware_scope=False)
  self.patches=[patch.object(c,'AUTHORITY',self.auth),patch.object(app_screen,'USB_AUTHORITY',Authority(clock=lambda:self.now)),patch.dict('os.environ',{'EPAPER_REMOTE_CONTROL':'1'})]
  for p in self.patches:p.start();self.addCleanup(p.stop)
  self.pair=Pairings(lambda t:c.owner(t)[3]);p=patch.object(c,'PAIRINGS',self.pair);p.start();self.addCleanup(p.stop)
  if hasattr(c,'USB_AUTHORITY'):
   p=patch.object(c,'USB_AUTHORITY',Authority(clock=lambda:self.now,firmware_scope=False));p.start();self.addCleanup(p.stop)
  if hasattr(c,'USB_SERIALS'):
   p=patch.object(c,'USB_SERIALS',{});p.start();self.addCleanup(p.stop)
 def request(self,path,obj,ticket=None):
  h=Handler(path,obj,ticket);handled=c.handle(h,self.config)
  self.assertTrue(handled,path);return h.code,h.data
 def proof(self,device='board',serial='aabbcc112233'):
  status,ch=self.request('usb-challenge',dict(device=device,serial=serial));self.assertEqual(status,200)
  nonce=ch['challenge'];key='secret' if device=='board' else 'other-secret'
  proof=hmac.new(key.encode(),b'pcusb-v1\n'+device.encode()+b'\n'+serial.upper().encode()+b'\n'+bytes.fromhex(nonce),hashlib.sha256).hexdigest()
  return dict(device=device,serial=serial,challenge=nonce,proof=proof)
 def grant(self):
  status,g=self.request('usb-authorize',self.proof());self.assertEqual(status,200);return g
 def test_authorize_renew_preserves_ticket_identity_and_pairing(self):
  g=self.grant();ticket=g['ticket'];identity=c.owner(ticket)
  self.assertEqual({k:g[k] for k in ('scope','serial','protocol','expiresIn')},dict(scope='phone-commands',serial='AABBCC112233',protocol='pcusb-v1',expiresIn=300))
  paired=self.pair.redeem(self.pair.issue_legacy(ticket)['code'])['ticket'];paired_identity=self.pair.owner(paired)
  self.now+=10;status,renew=self.request('usb-renew',self.proof(),ticket)
  self.assertEqual(status,200);self.assertEqual(renew['ticket'],ticket);self.assertEqual(c.owner(ticket),identity)
  self.assertEqual(self.pair.owner(paired),paired_identity);self.assertEqual(set(self.auth.tickets),{ticket})
 def test_replay_expiry_and_mismatch(self):
  obj=self.proof();self.assertEqual(self.request('usb-authorize',obj)[0],200);self.assertNotEqual(self.request('usb-authorize',obj)[0],200)
  obj=self.proof();self.now+=121;self.assertNotEqual(self.request('usb-authorize',obj)[0],200)
  for field,value in [('device','other'),('serial','000000000000'),('proof','0'*64)]:
   obj=self.proof();obj[field]=value;self.assertNotEqual(self.request('usb-authorize',obj)[0],200)
 def test_shape_rate_and_scopes_are_isolated(self):
  for serial in [None,1,'AA:BB:CC:11:22:33','a'*13,'a'*12+'\n']:
   self.assertNotEqual(self.request('usb-challenge',dict(device='board',serial=serial))[0],200)
  self.assertNotEqual(self.request('usb-challenge',dict(device='board',serial='a'*12,scope='screen-frames'))[0],200)
  obj=self.proof();self.assertNotEqual(self.request('authorize',{k:obj[k] for k in ('device','challenge','proof')})[0],200)
  ch=self.auth.challenge('board',{'board':'secret'});obj['challenge']=ch['challenge'];self.assertNotEqual(self.request('usb-authorize',obj)[0],200)
  ch=app_screen.USB_AUTHORITY.challenge('board',{'board':'secret'});obj['challenge']=ch['challenge'];self.assertNotEqual(self.request('usb-authorize',obj)[0],200)
  for _ in range(12):self.request('usb-challenge',dict(device='other',serial='a'*12))
  self.assertNotEqual(self.request('usb-challenge',dict(device='other',serial='a'*12))[0],200)
 def test_failed_renew_preserves_parent_and_superseded_cannot_revive(self):
  old=self.grant()['ticket'];obj=self.proof();obj['serial']='000000000000'
  self.assertNotEqual(self.request('usb-renew',obj,old)[0],200);c.owner(old)
  obj=self.proof();obj['proof']='0'*64;self.assertNotEqual(self.request('usb-renew',obj,old)[0],200);c.owner(old)
  new=self.grant()['ticket'];self.assertNotEqual(self.request('usb-renew',self.proof(),old)[0],200);c.owner(new)
  self.now+=301;self.assertNotEqual(self.request('usb-renew',self.proof(),new)[0],200)
 def test_concurrent_replay_has_one_winner(self):
  obj=self.proof()
  with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:self.request('usb-authorize',obj)[0],range(2)))
  self.assertEqual(results.count(200),1);self.assertEqual(len(self.auth.tickets),1)

 def test_ble_renew_cannot_extend_usb_parent(self):
  parent=self.grant()['ticket'];before=self.auth.tickets[parent]
  status,ch=self.request('challenge',{'device':'board'});self.assertEqual(status,200)
  proof=hmac.new(b'secret',b'PCFLASH1\nboard\n'+bytes.fromhex(ch['challenge']),hashlib.sha256).hexdigest()
  status,result=self.request('renew',dict(device='board',challenge=ch['challenge'],proof=proof),parent)
  self.assertEqual(status,403);self.assertEqual(self.auth.tickets[parent],before)
  self.assertEqual(self.request('usb-renew',self.proof(),parent)[0],200)
 def test_usb_validation_message_names_usb_without_private_proof(self):
  proof='private-proof-must-not-appear'
  status,result=self.request('usb-authorize',dict(device='board',serial='a'*12,challenge='0'*64,proof=proof))
  self.assertEqual(status,409);self.assertIn('USB',result['reply']);self.assertNotIn('蓝牙',result['reply']);self.assertNotIn(proof,json.dumps(result))
 def test_revoke_invalidates_parent_and_paired_controller(self):
  parent=self.grant()['ticket'];paired=self.pair.redeem(self.pair.issue_legacy(parent)['code'])['ticket']
  with patch.object(c.remote_http.REMOTE,'stop_device') as stop:
   status,result=self.request('usb-revoke',{},parent)
   self.assertEqual(status,200);self.assertTrue(result['serverCancelled']);self.assertFalse(result['stopConfirmed']);stop.assert_called_once_with('board')
  for ticket in (parent,paired):
   with self.assertRaises(PermissionError):c.controller_owner(ticket)
  self.assertNotIn(parent,c.USB_SERIALS)
  self.assertEqual(self.request('usb-revoke',{},parent)[0],403)
 def test_non_usb_scope_cannot_renew_or_revoke(self):
  for scope in ('phone-commands','screen-frames','firmware'):
   ticket='x'*43;self.auth.tickets[ticket]=(self.now+300,'board',scope)
   self.assertEqual(self.request('usb-revoke',{},ticket)[0],403)
   self.assertEqual(self.request('usb-renew',self.proof(),ticket)[0],403)
 def test_renew_expiring_during_proof_never_revives(self):
  parent=self.grant()['ticket'];obj=self.proof();original=c._usb_prove
  def expire(*args):
   answer=original(*args);self.now+=301;return answer
  with patch.object(c,'_usb_prove',side_effect=expire):
   self.assertEqual(self.request('usb-renew',obj,parent)[0],403)
  self.assertNotIn(parent,self.auth.tickets)
 def test_concurrent_renew_and_authorize_do_not_resurrect_old_parent(self):
  parent=self.grant()['ticket'];renew=self.proof();authorize=self.proof();barrier=threading.Barrier(2)
  def run(action):
   barrier.wait();return self.request('usb-'+action,renew if action=='renew' else authorize,parent if action=='renew' else None)
  with ThreadPoolExecutor(2) as pool:results=list(pool.map(run,('renew','authorize')))
  self.assertIn(results[0][0],(200,403));self.assertEqual(results[1][0],200)
  self.assertEqual(set(self.auth.tickets),{results[1][1]['ticket']});self.assertNotIn(parent,c.USB_SERIALS)

if __name__=='__main__':unittest.main()
