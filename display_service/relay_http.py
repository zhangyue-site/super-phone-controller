"""Short-lived App capability -> cloud signed BLE08 -> existing fenced mailbox."""
import json,os,threading
from pathlib import Path
from . import app_control,remote_http
from .hid_relay import Relay
from .keyboard_input import validate_command
from .usb_window import Windows,WindowExpired,capture_for,principal as capture_principal

class Gateway:
 def __init__(self,relay,remote,capture_for=lambda device:None):
  self.relay=relay;self.remote=remote;self.turns={};self.lock=threading.RLock()
  self.capture_for=capture_for;self.windows=Windows(clock=relay.clock);relay.mode_gate=self._mode_gate
 def _mode_gate(self,device,session,action):
  try:return self.windows.permit(device,self.capture_for(device),session['nonce'],(action['id'],action['seq'],action['op']))
  except WindowExpired:
   with self.relay.db:self.relay.db.execute('UPDATE actions SET state="failed" WHERE id=? AND state="queued"',(action['id'],))
   self.relay.detach(device,session['owner'],session['nonce'])
   self.windows.clear(device);self.turns.pop(device,None);self.remote.stop_device(device)
   raise
 def usb_window(self,device,capture,obj):
  with self.lock:
   if self.capture_for(device)!=capture:raise PermissionError('USB capture revoked')
   w=self.windows.windows.get(device)
   if w:
    self.relay._session(device,nonce=w['binding'])
   return self.windows.request(device,capture,obj)
 def direct_blocked(self,device):
  """Caller holds gateway.lock. Expiry consumes old work before handoff.

  Relay lock is released before Remote.stop_device takes its own locks.
  """
  with self.relay.lock:
   session=self.relay.sessions.get(device)
   if session:
    try:self.relay._session(device)
    except PermissionError:session=None
   active=session is not None
  if active:return True
  if device in self.turns:
   self.turns.pop(device,None);self.windows.clear(device)
   self.remote.stop_device(device)
  return False
 def attach(self,device,owner,receipt):
  with remote_http.OWNERSHIP_LOCK,self.lock:
   # Authenticate before examining ownership. Capability hints confer no lease.
   if not isinstance(receipt,dict):raise PermissionError("receipt shape")
   self.relay._verify(device,receipt.get("nonce",""),receipt)
   live=self.direct_blocked(device)
   previous=self.turns.get(device)
   if live and previous and previous["nonce"]==receipt["nonce"] and previous["owner"]==owner:
    return self.relay.attach(device,owner,receipt)
   # Remote.claim cannot race this pre-arm ownership check: direct HTTP claims
   # use OWNERSHIP_LOCK as well. Do not hold relay.lock while taking remote.lock.
   with self.remote.lock:
    self.remote._sync()
    if any(r["owner"][3]==device and r["state"]=="running" for r in self.remote.records.values()):raise ValueError("direct task running; gateway cannot preempt")
   result=self.relay.attach(device,owner,receipt)
   self.windows.clear(device)
   self.turns[device]=dict(owner=owner,nonce=receipt["nonce"],session=receipt["nonce"][:16],sequence=1,lease=None,command=None,action=None,job=None)
   return result
 def poll(self,device,owner,nonce):
  with self.lock:
   t=self.turns.get(device)
   if not t or t["owner"]!=owner or t["nonce"]!=nonce:raise PermissionError("gateway lease")
   packet=self.relay.poll(device,owner,nonce)
   if packet["state"]!="idle":return packet
   if t.get("otaRequested"):return packet
   s=self.relay._session(device,owner,nonce)
   # Only arm when a confirmed cloud task is waiting and screen consent exists.
   with self.remote.lock:
    self.remote._sync()
    queued=any(r["owner"][3]==device and r["state"]=="queued" for r in self.remote.records.values())
   if queued and self.remote.screen_ready(device) and not s["hid"]:
    self.relay.offer(device,6,[0]*5);return self.relay.poll(device,owner,nonce)
   if not s["hid"]:return packet
   if t["job"] is None and (not queued or not self.remote.screen_ready(device)):return packet
   if t["job"] is None:
    claim=self.remote.claim(device,t["session"],t["sequence"],True,"absolute-v1",t["lease"])
    if "lease" in claim:t["lease"]=claim["lease"]
    if claim.get("op")=="start":t["job"]=claim["task_id"]
    else:
     if "lease" not in claim:t["sequence"]+=1
     return packet
   state=self.remote.board_status(device,t["session"],t["sequence"])
   if state["op"]!="wait":
    t.pop("keyboard_remaining",None);t["command"]=None;t["action"]=None
    if state["op"]=="done":
     # Verified completion releases HID while preserving the authenticated target connection.
     t["normalComplete"]=self.relay.offer(device,7,[0]*5)
    else:self.relay.offer(device,5,[0]*5)
    return self.relay.poll(device,owner,nonce)
   if t.get("keyboard_remaining"):
    # A cancelled/expired mailbox must never leave the next fragment queued.
    with self.remote.c.mailbox.lock:
     self.remote.c.mailbox._job(device,t["session"],t["sequence"])
    op,args=t["keyboard_remaining"].pop(0)
    t["action"]=self.relay.offer(device,op,args)
    return self.relay.poll(device,owner,nonce)
   cmd=self.remote.c.mailbox.poll(device,t["session"],t["sequence"],"absolute-v1")
   if cmd["op"] in ("wait","done"):return packet
   if cmd["op"] in ("hid_key","hid_text"):
    try:fragments=validate_command(cmd)
    except (ValueError,TypeError):
     self.remote.c.mailbox.ack(device,t["session"],t["sequence"],cmd["id"],False,"","input_failed")
     raise
    op,args=fragments[0];t["keyboard_remaining"]=fragments[1:]
   elif cmd["op"]=="hid_home":op=1;args=[0]*5
   elif cmd["op"]=="hid_pointer":
    op=3 if cmd.get("kind")=="click" else 4 if cmd.get("kind")=="drag" else 0
    args=[cmd["x"],cmd["y"],cmd.get("x2",0),cmd.get("y2",0),cmd.get("duration_ms",0)]
   else:
    self.remote.c.mailbox.ack(device,t["session"],t["sequence"],cmd["id"],False,"","input_failed")
    raise ValueError("BLE08 does not support this action; no fallback input")
   t["command"]=cmd;t["action"]=self.relay.offer(device,op,args)
   return self.relay.poll(device,owner,nonce)
 def maintenance(self,device,owner,nonce,op):
  """One online, short-lived signing response; shares the HID sequence fence.

  Never queues behind or replaces a delivered command. The App must forward
  immediately and ACK the exact signed board receipt, never retry the packet.
  """
  if type(op) is not int or op not in (11,12):raise ValueError("maintenance op")
  with self.lock:
   t=self.turns.get(device)
   if not t or t["owner"]!=owner or t["nonce"]!=nonce:raise PermissionError("gateway lease")
   with self.relay.lock:
    s=self.relay._session(device,owner,nonce)
    if s["issued"] or self.relay.db.execute('SELECT 1 FROM actions WHERE device=? AND state="queued"',(device,)).fetchone():return {"state":"busy"}
    if op==11:
     with self.remote.lock:
      self.remote._sync()
      queued=any(r["owner"][3]==device and r["state"]=="queued" for r in self.remote.records.values())
     if s["hid"] or t["job"] is not None or queued or t.get("otaRequested"):return {"state":"busy"}
    self.relay.offer(device,op,[0]*5)
    result=self.relay.poll(device,owner,nonce)
    result["expiresIn"]=15
    if op==11:
     t["otaRequested"]=True
     result["otaComplete"]=False
    return result
 def ack(self,device,owner,nonce,ident,receipt):
  with self.lock:
   result=self.relay.ack(device,owner,nonce,ident,receipt)
   t=self.turns[device]
   if t["action"]==ident:
    cmd=t["command"];ok=result["state"]=="acknowledged"
    if ok and t.get("keyboard_remaining"):
     # Re-check live mailbox/STOP before issuing any later fragment. Never
     # advance directly in ack: the next poll must pass board_status first.
     t["action"]=None
     return result
    output={"hid_home":"HID_HOME_REPORT_SENT","hid_pointer":"HID_POINTER_REPORT_SENT","hid_key":"HID_KEY_REPORT_SENT","hid_text":"HID_TEXT_REPORT_SENT"}[cmd["op"]]
    t.pop("keyboard_remaining",None)
    self.remote.c.mailbox.ack(device,t["session"],t["sequence"],cmd["id"],ok,output if ok else "","" if ok else "input_failed")
    t["command"]=None;t["action"]=None
   if result["state"]=="acknowledged" and receipt["op"]==7 and t.get("normalComplete")==ident:
    # Relay.ack has already authenticated hid=0, ready=1 and the exact issued sequence.
    t.update(job=None,action=None,command=None,normalComplete=None,sequence=t["sequence"]+1)
   if receipt["op"]==5 or result["state"]=="failed":
    self.remote.stop_device(device);self.turns.pop(device,None);self.windows.clear(device)
   return result
 def detach(self,device,owner,nonce):
  with self.lock:
   self.relay.detach(device,owner,nonce);self.remote.stop_device(device);self.turns.pop(device,None);self.windows.clear(device)
   return {"state":"stopped","verified":False}

GATEWAY=None
INIT_LOCK=threading.Lock()
def gateway(config):
 global GATEWAY
 with INIT_LOCK:
  if GATEWAY is None:
   key_for=lambda d:json.loads(config.read_text())[d].encode()
   GATEWAY=Gateway(Relay(Path(os.environ.get("EPAPER_STATE","/var/lib/phone-controller"))/"hid-relay.sqlite3",key_for),remote_http.REMOTE,capture_for=capture_for)
 return GATEWAY

def _audit_failure(path,error):
 # Fixed fields only: never log Authorization, packets, receipts or request bodies.
 operation=path.rsplit('/',1)[-1]
 if operation not in ('attach','poll','ack','detach','maintenance','usb-window'):operation='unknown'
 known={'expired','auth','ticket','relay owner','relay expired; reconcile first','gateway lease','USB preparation superseded','USB preparation expired','USB capture revoked','capture ticket','USB capture owner','USB window expired','action pending','receipt shape','receipt range','board proof','board nonce','retired BLE nonce'}
 reason=str(error) if str(error) in known else 'other'
 print('RELAY_FAILURE '+json.dumps(dict(operation=operation,error_type=type(error).__name__,reason=reason)),flush=True)

def handle(handler,config):
 if not handler.path.startswith("/app-relay/"):return False
 try:
  if handler.command!="POST" or os.environ.get("EPAPER_RELAY_CONTROL")!="1":handler.reply(503,b"{}");return True
  header=handler.headers.get("Authorization","")
  if not header.startswith("Bearer "):raise PermissionError("auth")
  if handler.path=="/app-relay/usb-window":
   from . import app_screen
   try:device=app_screen.subject(header[7:])
   except ValueError as error:raise PermissionError('capture ticket') from error
   obj=remote_http.body(handler,4096)
   result=gateway(config).usb_window(device,capture_principal(header[7:]),obj)
   handler.reply(200,json.dumps(result).encode());return True
  identity=app_control.owner(header[7:]);device=identity[3];principal=identity[1]
  obj=remote_http.body(handler,4096);g=gateway(config);op=handler.path.rsplit("/",1)[1]
  fields={"attach":{"receipt"},"poll":{"nonce"},"ack":{"nonce","id","receipt"},"detach":{"nonce"},"maintenance":{"nonce","op"}}
  if op not in fields or set(obj)!=fields[op]:raise ValueError("relay fields")
  if op=="attach":result=g.attach(device,principal,obj["receipt"])
  elif op=="poll":result=g.poll(device,principal,obj["nonce"])
  elif op=="maintenance":result=g.maintenance(device,principal,obj["nonce"],obj["op"])
  elif op=="ack":result=g.ack(device,principal,obj["nonce"],obj["id"],obj["receipt"])
  else:result=g.detach(device,principal,obj["nonce"])
  handler.reply(200,json.dumps(result).encode())
 except PermissionError as error:
  _audit_failure(handler.path,error);handler.reply(403,b"{\"reply\":\"Relay authorization expired; reconnect safely\"}")
 except (ValueError,TypeError,KeyError) as error:
  _audit_failure(handler.path,error);handler.reply(409,b"{\"reply\":\"Relay stopped; reconcile before reconnect\"}")
 except OSError as error:
  _audit_failure(handler.path,error);handler.reply(503,b"{}")
 return True
