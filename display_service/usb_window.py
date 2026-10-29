"""Single-use capture preparation fence for intentional USB re-enumeration.

No bearer, BLE nonce or command packet is exposed to the capture client.
"""
import hashlib,secrets,time

class WindowExpired(ValueError):pass

def principal(ticket):return hashlib.sha256(ticket.encode()).hexdigest()

def capture_for(device):
 from . import app_screen
 with app_screen.AUTHORITY.lock:
  now=app_screen.AUTHORITY.clock();app_screen.AUTHORITY._prune(now)
  candidates=[(item[0],principal(ticket)) for ticket,item in app_screen.AUTHORITY.tickets.items() if item[1]==device]
 return max(candidates)[1] if candidates else None

class Windows:
 def __init__(self,clock=time.monotonic):self.clock=clock;self.windows={};self.generation=0
 def clear(self,device):self.windows.pop(device,None)
 def permit(self,device,capture,binding,action):
  w=self.windows.get(device)
  if w:
   if w['capture']!=capture or w['binding']!=binding or w['action']!=action:raise WindowExpired('USB preparation superseded')
   if self.clock()>=w['deadline']:raise WindowExpired('USB preparation expired')
   if w['ready']:
    self.clear(device);return True
   return False
  if capture is None:return True
  self.generation+=1
  self.windows[device]=dict(capture=capture,binding=binding,action=action,nonce=secrets.token_hex(16),mode='hid' if action[2]==6 else 'normal',generation=self.generation,deadline=self.clock()+5,ready=False)
  return False
 def request(self,device,capture,obj):
  operation=obj.get('operation')
  if operation=='poll' and set(obj)!={'operation'}:raise ValueError('USB window fields')
  if operation=='ready' and set(obj)!={'operation','nonce','mode','generation'}:raise ValueError('USB window fields')
  if operation not in ('poll','ready'):raise ValueError('USB window operation')
  w=self.windows.get(device)
  if not w:
   if operation=='ready':raise PermissionError('retired USB window')
   return {'state':'idle'}
  if w['capture']!=capture:raise PermissionError('USB capture owner')
  if self.clock()>=w['deadline']:raise PermissionError('USB window expired')
  if operation=='ready':
   if type(obj['generation']) is not int or (obj['nonce'],obj['mode'],obj['generation'])!=(w['nonce'],w['mode'],w['generation']) or w['ready']:raise PermissionError('USB window mismatch or replay')
   w['ready']=True;return {'state':'ready'}
  if w['ready']:return {'state':'ready'}
  return {k:w[k] for k in ('nonce','mode','generation')}|{'state':'prepare','expiresInMs':max(1,int((w['deadline']-self.clock())*1000))}
