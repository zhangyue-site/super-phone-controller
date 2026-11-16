"""Bounded diagnostic observations, never proof that projection is still running.

Callers hold the capture authority lock. Time is the server monotonic receive
clock, and every read rechecks the same capture capability and device grant.
No actuator, persistent storage, credential logging or client timestamp exists.
"""
import hashlib

MAX_AGE_SECONDS=5.0
MAX_ENTRIES=256

class ScreenStates:
 def __init__(self):self.entries={}
 @staticmethod
 def _key(ticket):return hashlib.sha256(ticket.encode()).digest()
 @staticmethod
 def _valid(ticket,device,grants,now):
  grant=grants.get(ticket)
  return bool(grant and grant[0]>now and grant[1]==device)
 def prune(self,grants,now):
  valid={self._key(ticket):grant[1] for ticket,grant in grants.items() if grant[0]>now}
  for key,(device,received,_,_) in list(self.entries.items()):
   if valid.get(key)!=device or not 0<=now-received<=MAX_AGE_SECONDS:self.entries.pop(key,None)
 def discard(self,ticket):self.entries.pop(self._key(ticket),None)
 def record(self,ticket,device,headers,now,grants):
  self.prune(grants,now)
  if not self._valid(ticket,device,grants,now):return
  keys=('X-Screen-Interactive','X-Screen-Keyguard-Locked')
  values=[headers.get(key) for key in keys]
  duplicates=hasattr(headers,'get_all') and any(len(headers.get_all(key,[]))!=1 for key in keys)
  if duplicates or any(type(value) is not str or value not in ('0','1') for value in values):
   self.discard(ticket);return
  self.entries[self._key(ticket)]=(device,now,values[0]=='1',values[1]=='1')
  while len(self.entries)>MAX_ENTRIES:
   oldest=min(self.entries,key=lambda key:self.entries[key][1]);self.entries.pop(oldest)
 def bind_job(self,job,ticket,device,now,grants):
  # Diagnostic association only. The first actual frame remains the sole
  # writer of screen_session and the source of all visual/action evidence.
  if job.device!=device or job.done or job.cancelled or job.screen_session:return
  current=[key for key,grant in grants.items() if grant[0]>now and grant[1]==device]
  if len(current)!=1 or current[0]!=ticket:return
  job.diagnostic_capture=(self._key(ticket),device)
 def ticket_for_job(self,job,device,now,grants):
  actual=job.screen_session
  if actual:return actual if self._valid(actual,device,grants,now) else None
  link=getattr(job,'diagnostic_capture',None)
  if not link or link[1]!=device:return None
  current=[ticket for ticket,grant in grants.items() if grant[0]>now and grant[1]==device]
  # Multiple valid captures cannot identify which phone reports this job.
  if len(current)!=1 or self._key(current[0])!=link[0]:return None
  return current[0]
 def read(self,ticket,device,now,grants):
  self.prune(grants,now)
  if not ticket or not self._valid(ticket,device,grants,now):return None
  item=self.entries.get(self._key(ticket))
  if not item or item[0]!=device:return None
  return dict(interactive=item[2],keyguard_locked=item[3],age_s=round(now-item[1],3))
