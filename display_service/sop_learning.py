"""Verified semantic SOP experience. No coordinates, frames or credentials."""
import hashlib,json,os,re,threading,time
from pathlib import Path
LOCK=threading.RLock()
class Library:
 def __init__(self,root):self.root=Path(root)/"sop-learning"
 def path(self,device):
  if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}",device):raise ValueError("device")
  return self.root/(device+".json")
 def read(self,device):
  empty=lambda:{"schema":1,"routes":{},"pages":{}}
  try:
   p=self.path(device)
   if p.stat().st_size>1000000:raise ValueError("learning size")
   a=json.loads(p.read_text())
   if not isinstance(a,dict) or type(a.get("schema"))is not int or a["schema"]!=1 or set(a)!={"schema","routes","pages"} or not isinstance(a["routes"],dict) or not isinstance(a["pages"],dict):raise ValueError("learning structure")
   for row in a["routes"].values():
    if not isinstance(row,dict) or row.get("operation") not in ("open","uninstall") or not isinstance(row.get("app"),str) or type(row.get("promoted"))is not bool or not isinstance(row.get("runs"),list) or any(not isinstance(v,str) for v in row["runs"]):raise ValueError("route structure")
    self.clean(row["method"])
   for row in a["pages"].values():
    if not isinstance(row,dict) or row.get("operation") not in ("open","uninstall") or type(row.get("promoted"))is not bool or not isinstance(row.get("runs"),list) or any(not isinstance(v,str) for v in row["runs"]):raise ValueError("page structure")
    self.clean([row["method"]])
   return a
  except FileNotFoundError:return empty()
  except (OSError,ValueError,TypeError,KeyError,AttributeError):
   print("SOP_LEARNING_CACHE_INVALID device="+device,flush=True);return empty()
 def write(self,device,a):
  self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
  p=self.path(device);tmp=p.with_suffix(".tmp")
  raw=json.dumps(a,ensure_ascii=False)
  if len(raw.encode())>1000000:raise ValueError("learning full")
  fd=os.open(tmp,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
  with os.fdopen(fd,"w") as f:f.write(raw);f.flush();os.fsync(f.fileno())
  tmp.replace(p)
 @staticmethod
 def key(req):return hashlib.sha256((req["operation"]+"\n"+req["app"]).encode()).hexdigest()[:24]
 @staticmethod
 def clean(method):
  if not isinstance(method,list) or not 1<=len(method)<=32:raise ValueError("semantic method")
  out=[]
  for row in method:
   if not isinstance(row,dict) or set(row)-{"sop","target","context","direction","changed","page_kind","visual"}:raise ValueError("only semantic SOP data may be learned")
   if row.get("sop") not in ("tap_text","tap_icon","hold_app","page","uninstall_entry","confirm_uninstall"):raise ValueError("unknown learned SOP")
   if row["sop"]=="page" and (row.get("changed")is not True or row.get("direction") not in ("left","right","up","down")):raise ValueError("unverified page transition")
   if any(not isinstance(t,str) or not 1<=len(t)<=80 for t in row.get("context",[])) or len(row.get("context",[]))>24:raise ValueError("SOP context")
   if "target" in row and (not isinstance(row["target"],str) or not 1<=len(row["target"])<=80):raise ValueError("SOP target")
   if "visual" in row:
    from .sop_context import valid
    if not valid(row["visual"]) or row.get("page_kind") not in ("launcher","folder","app","menu","dialog"):raise ValueError("invalid learned page precondition")
   out.append(dict(row))
  return out
 def record(self,device,req,run,method,*,verified,terminal):
  if verified is not True or terminal!="done":return
  method=self.clean(method)
  if not isinstance(run,str) or not run:raise ValueError("learning run")
  with LOCK:
   a=self.read(device);key=self.key(req)
   digest=hashlib.sha256(json.dumps([{k:v for k,v in r.items() if k not in ("context","visual")} for r in method],sort_keys=True).encode()).hexdigest()
   old=a["routes"].get(key,{})
   runs=old.get("runs",[]) if old.get("digest")==digest else []
   runs=list(dict.fromkeys(runs+[run]))[-8:]
   a["routes"][key]=dict(operation=req["operation"],app=req["app"],method=method,digest=digest,runs=runs,promoted=len(runs)>=2,updated=time.time())
   for row in method:
    if row["sop"]!="page":continue
    pk=hashlib.sha256(json.dumps([req["operation"],row["direction"],sorted(row.get("context",[]))],ensure_ascii=False).encode()).hexdigest()[:24]
    item=a["pages"].get(pk,dict(operation=req["operation"],method=row,runs=[]))
    item["runs"]=list(dict.fromkeys(item["runs"]+[run]))[-8:];item["promoted"]=len(item["runs"])>=2;a["pages"][pk]=item
   a["routes"]=dict(list(a["routes"].items())[-64:]);a["pages"]=dict(list(a["pages"].items())[-128:]);self.write(device,a)
 def route(self,device,req):
  with LOCK:
   item=self.read(device)["routes"].get(self.key(req),{})
   return self.clean(item["method"]) if item.get("promoted") else None
 def page(self,device,context,*,operation):
  actual=set(context)
  with LOCK:
   for item in reversed(list(self.read(device)["pages"].values())):
    expected=set(item["method"].get("context",[]))
    if item.get("promoted") and item["operation"]==operation and len(actual & expected)>=2 and len(actual & expected)/max(1,len(actual | expected))>=.65:return dict(item["method"])
  return None
 def invalidate(self,device,req,reason):
  with LOCK:
   a=self.read(device);item=a["routes"].get(self.key(req))
   if item:item.update(promoted=False,runs=[],last_failure=reason[:60]);self.write(device,a)

 def context_kind(self,device,context,visual,operation):
  from .sop_context import same
  actual=set(context)
  with LOCK:
   data=self.read(device)
   for route in data["routes"].values():
    if not route.get("promoted") or route["operation"]!=operation:continue
    for row in route["method"]:
     expected=set(row.get("context",[]))
     if len(actual & expected)>=2 and len(actual & expected)/max(1,len(actual | expected))>=.65 and same(row.get("visual"),visual):return row.get("page_kind")
  return None
