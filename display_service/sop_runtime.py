"""Composed phone SOPs: semantic planning, fresh locators, physical execution."""
import hashlib,io,json,os,re,time
from pathlib import Path
from PIL import Image,ImageChops,ImageFilter,ImageStat
from . import phone_ocr
from .sop_policy import parse,validate_step,ocr_target,box
from .sop_learning import Library
from .sop_context import describe,same as same_visual
from .sop_vision import plan
from .skill_engine import matches,region,region_matches

def enabled(task):return os.environ.get("EPAPER_PHONE_SOP")=="1" and parse(task) is not None

def labels(hint):
 return sorted({r["text"].strip() for r in hint["lines"] if 1<=len(r["text"].strip())<=30 and not re.search(r"[0-9]|屏幕共享|共享中",r["text"])})[:24]
def overlap(a,b):
 a,b=set(a),set(b)
 return len(a & b)/max(1,len(a | b))

def fresh(nav,j,after,read_only=False):
 """One stable pair, not two pairs; dispatch still rechecks the latest frame."""
 raw,seq,sig=nav._frame(j,after=after)
 for _ in range(8):
  new,nseq,nsig=nav._frame(j,after=seq)
  if (sig["w"],sig["h"])!=(nsig["w"],nsig["h"]):raise ValueError("共享画面尺寸改变")
  if read_only or matches(sig,nsig):
   hint=phone_ocr.frame_hint(nav.m,j,new)
   if hint is None:hint=dict(width=nsig["w"],height=nsig["h"],lines=[],source="ocr-unavailable")
   return new,nseq,nsig,hint
  raw,seq,sig=new,nseq,nsig
 raise ValueError("画面未稳定，未发出下一步输入")

def normalized(b,w,h):return [v*1000//(w if i%2==0 else h) for i,v in enumerate(b)]

def blank_page(raw,hint,direction):
 """Re-locate a fresh blank gesture path, never reuse stored coordinates."""
 w,h=hint["width"],hint["height"]
 if direction not in ("left","right","up","down"):return None
 with Image.open(io.BytesIO(raw)) as im:
  gray=im.convert("L")
  for band in (.22,.32,.43,.55,.66):
   y=int(h*band);left=int(w*.15);right=int(w*.85)
   if any(r["bounds"][1]<=y+12 and r["bounds"][3]>=y-12 for r in hint["lines"]):continue
   stripe=gray.crop((left,y-8,right,y+8))
   if ImageStat.Stat(ImageChops.difference(stripe,stripe.filter(ImageFilter.GaussianBlur(2)))).mean[0]>1.5:continue
   if direction in ("left","right"):
    a,z=(right,left) if direction=="left" else (left,right)
    return dict(sop="page",target="当前页面空白间隙",locator="region",bounds=[max(0,a-5),y-5,min(w,a+5),y+5],end=[z,y],direction=direction)
 # Vertical pagination needs its own current image planning, never guess a column.
 return None

def command(step,b,w,h):
 x=(b[0]+b[2])*32767//(2*w);y=(b[1]+b[3])*32767//(2*h)
 c=dict(op="hid_pointer",kind="click",x=x,y=y)
 if step["sop"]=="hold_app":c.update(kind="drag",x2=x,y2=y,duration_ms=1000)
 if step["sop"]=="page":
  ex,ey=step["end"];dx=ex-(b[0]+b[2])/2;dy=ey-(b[1]+b[3])/2
  direction=("right" if dx>0 else "left") if abs(dx)/w>abs(dy)/h else ("down" if dy>0 else "up")
  if max(abs(dx)/w,abs(dy)/h)<.12 or step.get("direction")!=direction:raise ValueError("翻页方向或距离不一致")
  c.update(kind="drag",x2=ex*32767//w,y2=ey*32767//h,duration_ms=500)
 return c

def valid_final(final,req,hint):
 valid=final.get("safe")is True and final.get("operation")==req["operation"] and final.get("done")is True and final.get("verified")is True and final.get("application")==req["app"] and isinstance(final.get("evidence"),str) and bool(final["evidence"].strip()) and not final.get("steps")
 if req["operation"]=="uninstall" and any(r["text"].strip()==req["app"] or "卸载" in r["text"] for r in hint["lines"]):return False
 return valid

def run(nav,j,task,planner=plan):
 req=parse(task)
 if req is None:raise ValueError("当前SOP只接受明确打开或卸载指定应用")
 lib=Library(nav.store.root);method=[];history=[];metrics=dict(model_calls=0,model_ms=0,ocr_hits=0,image_hits=0,route_hits=0,page_hits=0,commands=0,frame_ms=0)
 j.sop_metrics=metrics;j.sop_pending=dict(library=lib,request=req,method=method,used_route=False)
 started=time.monotonic();phase="locate";last=0;queue=[];grounding=None;route=[];used_route=False;pending_page=None;misses=0
 def emit(event,**data):
  row=dict(task=getattr(j,"remote_task_id",""),event=event,phase=phase,ms=int((time.monotonic()-started)*1000),**data)
  print("PHONE_SOP "+json.dumps(row,ensure_ascii=False,separators=(",",":")),flush=True)
  j.sop_audit=getattr(j,"sop_audit",[])+[row]
 def read():
  nonlocal last
  t=time.monotonic();raw,seq,sig,hint=fresh(nav,j,last,read_only=phase in ("verify","after"));last=seq;metrics["frame_ms"]+=int((time.monotonic()-t)*1000)
  return raw,seq,sig,hint
 def ask(raw,hint,verify=False):
  t=time.monotonic();metrics["model_calls"]+=1
  out=planner(raw,hint,req,phase,history,verify=verify)
  metrics["model_ms"]+=int((time.monotonic()-t)*1000)
  if out.get("safe") is not True or out.get("operation")!=req["operation"]:raise ValueError("模型规划不属于当前授权任务")
  if out.get("screen") not in ("launcher","folder","app","menu","dialog"):raise ValueError("当前页面未知，未执行输入")
  if not verify and req["operation"]=="open" and out.get("screen")=="app" and out.get("steps"):raise ValueError("打开任务进入应用后仅允许结果核验")
  if not verify and out.get("screen")=="dialog" and not (req["operation"]=="uninstall" and phase=="confirm"):raise ValueError("当前出现非任务授权对话框，未执行输入")
  permitted={"locate":("launcher","folder"),"menu":("menu",),"app_info":("app",),"confirm":("dialog",)}.get(phase,())
  if not verify and out.get("steps") and out.get("screen") not in permitted:raise ValueError("当前页面不满足SOP导航阶段前提")
  return out
 def execute(c,sig):
  # No input replay adapter: explicit failure/unknown receipt stops this SOP.
  from .wechat_nav import WechatNavigator
  receipt=WechatNavigator._action(nav,j,c,sig) if isinstance(nav,WechatNavigator) else nav._action(j,c,sig)
  metrics["commands"]+=1
  if not isinstance(receipt,dict) or receipt.get("ok")is not True:raise ValueError("动作未收到肯定回执")
  return receipt
 nav.store.invalidate(j.device);j.fenced=True
 raw,seq,sig=nav._frame(j);execute(dict(op="hid_home"),sig);last=nav._receipt_frame_floor(j,seq)
 raw,seq,sig,hint=read();execute(dict(op="hid_home"),sig);last=nav._receipt_frame_floor(j,seq)
 emit("entry_home_normalized")
 try:route=lib.route(j.device,req) or []
 except (OSError,ValueError):emit("learning_unavailable")
 for index in range(20):
  nav.m._live(j)
  if time.monotonic()-started>160:raise ValueError("SOP任务达到执行时限")
  raw,seq,sig,hint=read();ctx=labels(hint);visual=describe(raw)
  current_kind=lib.context_kind(j.device,ctx,visual,req["operation"])
  allowed_kinds={"locate":("launcher","folder"),"menu":("menu",),"app_info":("app",),"confirm":("dialog",)}.get(phase,())
  if queue and current_kind not in allowed_kinds:
   queue=[];emit("future_page_requires_planner")
  page_observation=None
  if pending_page is not None:
   before,row=pending_page;changed=overlap(before,ctx)<.82
   history.append(dict(sop="page",direction=row["direction"],changed=changed));emit("page_result",changed=changed)
   page_observation=(row,changed)
   if not changed:queue=[];route=[]
   pending_page=None
  if phase in ("verify","after"):
   try:final=ask(raw,hint,verify=True)
   except Exception as error:
    from .general_vision import VisionTransportError
    if not isinstance(error,VisionTransportError):raise
    j.sop_verification_timeout=True;emit("verification_timeout",input_replayed=False)
    raise ValueError("点击指令已有回执；结果核验超时或连接失败，任务已结束，未重复点击。") from error
   if not valid_final(final,req,hint):raise ValueError("独立新画面未核验到目标结果")
   if req["operation"]=="uninstall":
    newer,nseq,nsig,nhint=read()
    if not matches(sig,nsig):
     final=ask(newer,nhint,verify=True)
     if not valid_final(final,req,nhint):raise ValueError("结果画面发生变化，复核未通过")
   with nav.m.lock:nav.m._live(j);j.navigation_verified=True
   j.sop_pending["used_route"]=used_route
   emit("verified",result_frame=seq,result_sha256=hashlib.sha256(raw).hexdigest(),metrics=metrics,elapsed_ms=int((time.monotonic()-started)*1000))
   return ("已打开"+req["app"]+"，已核验本次画面。"+("当前停在提示页，未继续操作。" if final.get("screen")=="dialog" else "")) if req["operation"]=="open" else "已核验完成："+task+"。"
  def accept_page(kind):
   nonlocal page_observation
   if page_observation is None:return
   row,changed=page_observation
   if changed and kind==row.get("page_kind") and kind in ("launcher","folder","app"):method.append(dict(row,changed=True))
   else:emit("page_transition_not_learned",observed_kind=kind)
   page_observation=None
  if current_kind is not None:accept_page(current_kind)
  origin="model"
  if not queue and route:
   row=route[0]
   if row["sop"] in ("tap_text","hold_app") and current_kind in allowed_kinds and row.get("page_kind")==current_kind and same_visual(row.get("visual"),visual) and overlap(row.get("context",[]),ctx)>=.65 and ocr_target(hint,row.get("target")) is not None:
    queue=[dict(sop=row["sop"],target=row["target"],locator="text",bounds=None)];route.pop(0);origin="route";metrics["route_hits"]+=1;used_route=True;j.sop_pending["used_route"]=True
   elif row["sop"]=="page" and current_kind in allowed_kinds and row.get("page_kind")==current_kind and same_visual(row.get("visual"),visual) and overlap(row.get("context",[]),ctx)>=.65 and ocr_target(hint,req["app"]) is None:
    step=blank_page(raw,hint,row["direction"])
    if step:queue=[step];route.pop(0);origin="route";metrics["route_hits"]+=1;used_route=True;j.sop_pending["used_route"]=True
    else:route=[]
   else:route=[]
  if not queue:
   learned=None
   try:learned=lib.page(j.device,ctx,operation=req["operation"])
   except (OSError,ValueError):pass
   if learned and current_kind in allowed_kinds and learned.get("page_kind")==current_kind and same_visual(learned.get("visual"),visual) and phase=="locate" and metrics["page_hits"]<3 and ocr_target(hint,req["app"]) is None:
    step=blank_page(raw,hint,learned["direction"])
    if step:queue=[step];origin="page_skill";metrics["page_hits"]+=1
  if not queue:
   out=ask(raw,hint);current_kind=out.get("screen");accept_page(current_kind)
   if out.get("done")is True:
    # A planning response cannot authorize its own completion.
    phase="verify" if req["operation"]=="open" else phase
    if req["operation"]!="open":raise ValueError("尚未取得卸载确认回执，不能声称完成")
    continue
   queue=list(out.get("steps",[]))
   if not queue:raise ValueError("模型未给出可执行的有界SOP")
   grounding=(raw,sig,hint)
   emit("plan",steps=[{k:s.get(k) for k in ("sop","target","locator")} for s in queue])
   # All current coordinates must survive a genuinely later frame.
   raw,seq,sig,hint=read();ctx=labels(hint)
  step=queue.pop(0)
  step=validate_step(step,req,hint,phase)
  if grounding is not None:
   old,oldsig,oldhint=grounding;grounding=None
   if not matches(oldsig,sig):
    b=step.get("bounds") or ocr_target(oldhint,step["target"])
    stable=bool(b and same_visual(describe(old),describe(raw)) and overlap(labels(oldhint),ctx)>=.65 and region_matches(region(old,normalized(b,oldhint["width"],oldhint["height"])),raw))
    if not stable:queue=[];emit("plan_frame_changed");continue
  b=ocr_target(hint,step["target"],step.get("bounds")) if step["locator"]=="text" else step.get("bounds")
  if b is None:
   misses+=1;queue=[];route=[];history.append(dict(sop=step["sop"],target=step["target"],result="OCR不唯一或未找到，未执行"));emit("locator_miss",target=step["target"])
   if misses>=3:raise ValueError("OCR目标连续无法唯一定位，已停止")
   continue
  box(b,hint["width"],hint["height"])
  if step["locator"]=="text":metrics["ocr_hits"]+=1
  else:metrics["image_hits"]+=1
  c=command(step,b,hint["width"],hint["height"])
  sig["target"]=region(raw,normalized(b,hint["width"],hint["height"]));sig["_visual_target"]=True;sig["_observation_frame"]=seq
  emit("locate",sop=step["sop"],target=step["target"],reader="phone_ocr" if step["locator"]=="text" else "current_image",origin=origin,frame=seq)
  execute(c,sig);last=nav._receipt_frame_floor(j,seq)
  row=dict(sop=step["sop"],target=step["target"],context=ctx,page_kind=current_kind,visual=describe(raw))
  if step["sop"]=="page":
   row.pop("target");row["direction"]=step["direction"];pending_page=(ctx,row)
  else:method.append(row)
  history.append(dict(sop=step["sop"],target=step["target"],receipt="confirmed"))
  emit("receipt",sop=step["sop"],target=step["target"])
  if step["sop"]=="hold_app":phase="menu";queue=[]
  elif step["sop"]=="uninstall_entry":phase="confirm";queue=[]
  elif step["sop"]=="confirm_uninstall":phase="after";queue=[]
  elif step["target"]==req["app"] and req["operation"]=="open":phase="verify";queue=[];j.sop_action_acknowledged=True;j.reply="点击已有回执，正在核验应用画面。"
  elif step["target"] in ("应用信息","应用详情","应用信息图标") and req["operation"]=="uninstall":phase="app_info"
 raise ValueError("SOP超过有界步骤限制")

def finalize(job,mailbox):
 pending=getattr(job,"sop_pending",None)
 if not pending:return
 with mailbox.lock:
  success=job.done and job.state=="done" and job.navigation_verified and not job.cancelled
  lib,req=pending["library"],pending["request"]
  try:
   if success:lib.record(job.device,req,getattr(job,"remote_task_id","") or str(job.sequence),pending["method"],verified=True,terminal="done")
   elif pending.get("used_route"):lib.invalidate(job.device,req,"execution_not_verified")
   print("SOP_LEARNING "+json.dumps(dict(task=getattr(job,"remote_task_id",""),committed=success,operation=req["operation"],app=req["app"],promoted=lib.route(job.device,req) is not None)),flush=True)
  except (OSError,ValueError) as error:print("SOP_LEARNING "+json.dumps(dict(committed=False,error=type(error).__name__)),flush=True)
  root=os.environ.get("EPAPER_NAV_EVIDENCE_DIR");ident=getattr(job,"remote_task_id","")
  if root and re.fullmatch("[a-f0-9]{32}",ident):
   try:
    p=Path(root)/ident;p.mkdir(mode=0o700,parents=True,exist_ok=True)
    out=dict(task=ident,verified=success,request=req,metrics=getattr(job,"sop_metrics",{}),events=getattr(job,"sop_audit",[]));f=p/"sop.json";f.write_text(json.dumps(out,ensure_ascii=False,indent=2));f.chmod(0o600)
   except OSError:pass
 job.sop_pending=None
