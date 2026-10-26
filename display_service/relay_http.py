"""Short-lived App capability -> cloud signed BLE08 -> existing fenced mailbox."""
import json,os,threading
from pathlib import Path
from . import app_control,remote_http
from .hid_relay import Relay

class Gateway:
 def __init__(self,relay,remote):self.relay=relay;self.remote=remote;self.turns={};self.lock=threading.RLock()
 def attach(self,device,owner,receipt):
  with self.lock:
   result=self.relay.attach(device,owner,receipt)
   if device in self.turns and self.turns[device]["nonce"]==receipt["nonce"] and self.turns[device]["owner"]==owner:return result
   self.turns[device]=dict(owner=owner,nonce=receipt["nonce"],session=receipt["nonce"][:16],sequence=1,lease=None,command=None,action=None,job=None)
   return result
 def poll(self,device,owner,nonce):
  with self.lock:
   t=self.turns.get(device)
   if not t or t["owner"]!=owner or t["nonce"]!=nonce:raise PermissionError("gateway lease")
   packet=self.relay.poll(device,owner,nonce)
   if packet["state"]!="idle":return packet
   s=self.relay._session(device,owner,nonce)
   # Only arm when a confirmed cloud task is waiting and screen consent exists.
   with self.remote.lock:
    self.remote._sync()
    queued=any(r["owner"][3]==device and r["state"]=="queued" for r in self.remote.records.values())
   if queued and self.remote.screen_ready(device) and not s["hid"]:
    self.relay.offer(device,6,[0]*5);return self.relay.poll(device,owner,nonce)
   if not s["hid"]:return packet
   if t["job"] is None:
    claim=self.remote.claim(device,t["session"],t["sequence"],True,"absolute-v1",t["lease"])
    if "lease" in claim:t["lease"]=claim["lease"]
    if claim.get("op")=="start":t["job"]=claim["task_id"]
    else:return packet
   state=self.remote.board_status(device,t["session"],t["sequence"])
   if state["op"]!="wait":
    self.relay.offer(device,5,[0]*5);return self.relay.poll(device,owner,nonce)
   cmd=self.remote.c.mailbox.poll(device,t["session"],t["sequence"],"absolute-v1")
   if cmd["op"] in ("wait","done"):return packet
   if cmd["op"]=="hid_home":op=1;args=[0]*5
   elif cmd["op"]=="hid_pointer":
    op=3 if cmd.get("kind")=="click" else 4 if cmd.get("kind")=="drag" else 0
    args=[cmd["x"],cmd["y"],cmd.get("x2",0),cmd.get("y2",0),cmd.get("duration_ms",0)]
   else:
    self.remote.c.mailbox.ack(device,t["session"],t["sequence"],cmd["id"],False,"","input_failed")
    raise ValueError("BLE08 does not support this action; no fallback input")
   t["command"]=cmd;t["action"]=self.relay.offer(device,op,args)
   return self.relay.poll(device,owner,nonce)
 def ack(self,device,owner,nonce,ident,receipt):
  with self.lock:
   result=self.relay.ack(device,owner,nonce,ident,receipt)
   t=self.turns[device]
   if t["action"]==ident:
    cmd=t["command"];ok=result["state"]=="acknowledged"
    output="HID_HOME_REPORT_SENT" if cmd["op"]=="hid_home" else "HID_POINTER_REPORT_SENT"
    self.remote.c.mailbox.ack(device,t["session"],t["sequence"],cmd["id"],ok,output if ok else "","" if ok else "input_failed")
    t["command"]=None;t["action"]=None
   if receipt["op"]==5 or result["state"]=="failed":self.remote.stop_device(device);self.turns.pop(device,None)
   return result
 def detach(self,device,owner,nonce):
  with self.lock:
   self.relay.detach(device,owner,nonce);self.remote.stop_device(device);self.turns.pop(device,None)
   return {"state":"stopped","verified":False}

GATEWAY=None
INIT_LOCK=threading.Lock()
def gateway(config):
 global GATEWAY
 with INIT_LOCK:
  if GATEWAY is None:
   key_for=lambda d:json.loads(config.read_text())[d].encode()
   GATEWAY=Gateway(Relay(Path(os.environ.get("EPAPER_STATE","/var/lib/phone-controller"))/"hid-relay.sqlite3",key_for),remote_http.REMOTE)
 return GATEWAY

def handle(handler,config):
 if not handler.path.startswith("/app-relay/"):return False
 try:
  if handler.command!="POST" or os.environ.get("EPAPER_RELAY_CONTROL")!="1":handler.reply(503,b"{}");return True
  header=handler.headers.get("Authorization","")
  if not header.startswith("Bearer "):raise PermissionError("auth")
  identity=app_control.owner(header[7:]);device=identity[3];principal=identity[1]
  obj=remote_http.body(handler,4096);g=gateway(config);op=handler.path.rsplit("/",1)[1]
  fields={"attach":{"receipt"},"poll":{"nonce"},"ack":{"nonce","id","receipt"},"detach":{"nonce"}}
  if op not in fields or set(obj)!=fields[op]:raise ValueError("relay fields")
  if op=="attach":result=g.attach(device,principal,obj["receipt"])
  elif op=="poll":result=g.poll(device,principal,obj["nonce"])
  elif op=="ack":result=g.ack(device,principal,obj["nonce"],obj["id"],obj["receipt"])
  else:result=g.detach(device,principal,obj["nonce"])
  handler.reply(200,json.dumps(result).encode())
 except PermissionError:handler.reply(403,b"{\"reply\":\"Relay authorization expired; reconnect safely\"}")
 except (ValueError,TypeError,KeyError):handler.reply(409,b"{\"reply\":\"Relay stopped; reconcile before reconnect\"}")
 except OSError:handler.reply(503,b"{}")
 return True
