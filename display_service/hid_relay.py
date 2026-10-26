"""Cloud-owned BLE08 packets. Gateway never receives the device/session key.

A delivered packet is consumed durably before HTTP returns. Missing ACK is
uncertain, never retried. This transport does not claim screen verification.
"""
import hashlib,hmac,json,os,re,sqlite3,struct,threading,time,uuid
from pathlib import Path

EXPECTED={1:3,2:3,3:3,4:3,5:5,6:7,7:8}
class Relay:
 def __init__(self,path,key_for,clock=time.monotonic):
  path=Path(path);path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
  self.db=sqlite3.connect(path,check_same_thread=False);os.chmod(path,0o600)
  self.db.row_factory=sqlite3.Row;self.db.execute("PRAGMA journal_mode=WAL");self.db.execute("PRAGMA synchronous=FULL")
  self.db.execute("CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY,device TEXT,nonce TEXT,seq INTEGER,op INTEGER,args TEXT,state TEXT,receipt TEXT)")
  with self.db:self.db.execute("UPDATE actions SET state=\"uncertain\" WHERE state IN (\"queued\",\"issued\")")
  self.db.execute("CREATE TABLE IF NOT EXISTS connections(nonce TEXT PRIMARY KEY,device TEXT)")
  self.key_for=key_for;self.clock=clock;self.lock=threading.RLock();self.sessions={}
 def _key(self,device,nonce):
  return hmac.new(self.key_for(device),("PCBLE1\n"+device+"\n"+nonce).encode(),hashlib.sha256).digest()
 def _verify(self,device,nonce,d):
  if not isinstance(d,dict) or d.get("nonce")!=nonce or not re.fullmatch("[0-9a-f]{32}",nonce):raise PermissionError("board nonce")
  fields=("seq","op","result","hid","busy","ready")
  if any(type(d.get(k)) is not int for k in fields):raise PermissionError("receipt shape")
  if not 0<=d["seq"]<=0xffffffff or not 0<=d["op"]<=7 or not 0<=d["result"]<=8 or any(d[k] not in (0,1) for k in ("hid","busy","ready")):raise PermissionError("receipt range")
  text="PCBLE1-ACK\n"+nonce+"".join("\n"+str(d[k]) for k in fields)
  proof=d.get("proof")
  if not isinstance(proof,str) or not hmac.compare_digest(proof,hmac.new(self._key(device,nonce),text.encode(),hashlib.sha256).hexdigest()):raise PermissionError("board proof")
 def attach(self,device,owner,receipt):
  if not isinstance(receipt,dict):raise PermissionError("receipt shape")
  nonce=receipt.get("nonce","");self._verify(device,nonce,receipt)
  if receipt["seq"]!=0 or receipt["op"]!=0 or receipt["result"]!=0 or receipt["busy"] or not receipt["ready"]:raise PermissionError("fresh idle connection required")
  with self.lock:
   old=self.sessions.get(device)
   if old and self.clock()-old["touched"]>15:
    try:self._session(device)
    except PermissionError:pass
    old=None
   if old:
    if old["nonce"]==nonce and old["owner"]==owner:return {"state":"connected","nonce":nonce}
    raise PermissionError("device already leased")
   try:
    with self.db:self.db.execute("INSERT INTO connections VALUES(?,?)",(nonce,device))
   except sqlite3.IntegrityError as error:raise PermissionError("retired BLE nonce") from error
   self.sessions[device]=dict(nonce=nonce,owner=owner,seq=0,touched=self.clock(),issued=None,hid=receipt["hid"],safety_reset=bool(receipt["hid"]))
   if receipt["hid"]:self.offer(device,7,[0]*5)
   return {"state":"connected","nonce":nonce}
 def _session(self,device,owner=None,nonce=None):
  s=self.sessions.get(device)
  if not s or (owner is not None and s["owner"]!=owner) or (nonce is not None and s["nonce"]!=nonce):raise PermissionError("relay owner")
  if self.clock()-s["touched"]>15:
   with self.db:self.db.execute("UPDATE actions SET state=\"uncertain\" WHERE device=? AND state IN (\"queued\",\"issued\")",(device,))
   del self.sessions[device];raise PermissionError("relay expired; reconcile first")
  return s
 @staticmethod
 def validate(op,args):
  if type(op) is not int or op not in EXPECTED or not isinstance(args,(list,tuple)) or len(args)!=5 or any(type(n) is not int for n in args):raise ValueError("action shape")
  valid=all(0<=n<=32767 for n in args[:2]) and list(args[2:])==[0,0,0] if op==3 else all(0<=n<=32767 for n in args[:4]) and 100<=args[4]<=1200 if op==4 else list(args)==[0]*5
  if not valid:raise ValueError("action parameters")
 def offer(self,device,op,args):
  self.validate(op,args)
  with self.lock:
   s=self._session(device)
   if s["issued"] or self.db.execute("SELECT 1 FROM actions WHERE device=? AND state=\"queued\"",(device,)).fetchone():raise ValueError("action pending")
   if s.get("safety_reset") and op!=7:raise ValueError("safe reset must be acknowledged first")
   if op in (1,2,3,4) and not s["hid"]:raise ValueError("HID not armed")
   if s["seq"]>=0xffffffff:raise ValueError("sequence exhausted")
   i=uuid.uuid4().hex;s["seq"]+=1
   with self.db:self.db.execute("INSERT INTO actions VALUES(?,?,?,?,?,?,?,?)",(i,device,s["nonce"],s["seq"],op,json.dumps(args),"queued",None))
   return i
 def poll(self,device,owner,nonce):
  with self.lock:
   s=self._session(device,owner,nonce)
   # Polling must not keep a lost action alive forever.
   if s["issued"]:return {"state":"awaiting_receipt"}
   s["touched"]=self.clock()
   r=self.db.execute("SELECT * FROM actions WHERE device=? AND nonce=? AND state=\"queued\" ORDER BY seq LIMIT 1",(device,nonce)).fetchone()
   if not r:return {"state":"idle"}
   body=struct.pack("<BBI5H",1,r["op"],r["seq"],*json.loads(r["args"]))
   wire=body+hmac.new(self._key(device,nonce),body,hashlib.sha256).digest()
   with self.db:self.db.execute("UPDATE actions SET state=\"issued\" WHERE id=?",(r["id"],))
   s["issued"]=r["id"]
   return dict(state="action",id=r["id"],seq=r["seq"],op=r["op"],packet=wire.hex())
 def ack(self,device,owner,nonce,ident,receipt):
  with self.lock:
   s=self._session(device,owner,nonce);self._verify(device,nonce,receipt)
   if s["issued"]!=ident:raise ValueError("unexpected action ACK")
   r=self.db.execute("SELECT * FROM actions WHERE id=?",(ident,)).fetchone()
   if (receipt["seq"],receipt["op"])!=(r["seq"],r["op"]) or receipt["busy"]:raise ValueError("receipt mismatch")
   success=receipt["result"]==EXPECTED[r["op"]]
   if success and r["op"] in (6,7) and (not receipt["ready"] or receipt["hid"]!=(1 if r["op"]==6 else 0)):raise ValueError("USB mode not settled")
   with self.db:self.db.execute("UPDATE actions SET state=?,receipt=? WHERE id=?",("acknowledged" if success else "failed",json.dumps(receipt),ident))
   s.update(issued=None,touched=self.clock(),hid=receipt["hid"])
   if success and r["op"]==7:s["safety_reset"]=False
   if not success or r["op"]==5:del self.sessions[device]
   return {"state":"acknowledged" if success else "failed","verified":False}
 def status(self,ident):
  with self.lock:
   r=self.db.execute("SELECT id,state,seq,op FROM actions WHERE id=?",(ident,)).fetchone()
   if not r:raise ValueError("unknown action")
   return dict(r)
 def detach(self,device,owner,nonce):
  with self.lock:
   self._session(device,owner,nonce)
   with self.db:self.db.execute("UPDATE actions SET state=\"uncertain\" WHERE device=? AND state IN (\"queued\",\"issued\")",(device,))
   del self.sessions[device]
 def close(self):self.db.close()
