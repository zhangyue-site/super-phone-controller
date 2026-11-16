"""Bind a generic task to its authenticated owner, device and live screen lease."""
import time,re,json,hashlib,os
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from .agent_contract import Authority
from .agent_runtime import REGISTRY
from .agent_capabilities import is_commit_label
def policy(info,step,hint):
 target=step.get("target","")
 if step.get("capability")=="edge_swipe" and info.get("_platform")!="android":return False
 if step.get("capability")=="back" and step.get("locator")=="none":
  return bool(info.get("_platform")=="android" and info.get("original") and hint.get("lines") is not None)
 if step.get("capability") in ("type_text","adjust_brightness"):
  from .agent_controls import authorize
  return authorize(info.get("original",""),step,info.get("_control_history",[]))
 if step.get("capability")=="dismiss":return target in ("下次再说","暂不开通","不同意","取消","关闭","稍后","返回","关闭弹窗")
 if step.get("capability")=="save_record":
  return bool(re.search(r"保存|记账|录入|登记|save|record",info.get("original",""),re.I))
 if step.get("capability") not in REGISTRY:return False
 if is_commit_label(target) and step.get("capability")!="save_record":return False
 if re.search(r"转账|付款|支付密码|立即支付|购买|下单|发消息|发送|删除|授权|同意|允许|登录|注册",target):return False
 return bool(info.get("original") and hint.get("lines") is not None)
def context_key(owner,text):
 return hashlib.sha256(json.dumps([owner,text],ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
def try_existing_uninstall(nav,job,original,understanding,*,platform,authority,guard,runner=None,clock=time.monotonic):
 from .agent_existing_skills import verify_intent,run as old_sop
 request=verify_intent(original,understanding,platform)
 if request is None:return None
 def check():
  if not isinstance(authority,Authority) or "uninstall_app" not in authority.capabilities:
   raise ValueError("旧卸载SOP缺少外部能力授权")
  if (authority.goal_id,authority.device,authority.session)!=(getattr(job,"remote_task_id",None),job.device,job.screen_session):
   raise ValueError("旧卸载SOP任务或共享绑定失效")
  nav.m._live(job)
  if clock()>=authority.expires or guard(authority) is not True:
   job.navigation_verified=False
   raise ValueError("旧卸载SOP入口授权或租约已失效")
 class GuardedNavigator:
  # Do not replace the shared Mailbox._live: another task may be running.
  # Keep its lock ordering and per-input fences, and check the remote grant at
  # this task's frame/action boundaries, including after long model waits.
  def __getattr__(self,name):return getattr(nav,name)
  def _frame(self,current,*args,**kwargs):
   if current is not job:raise ValueError("旧卸载SOP不能观察其他任务")
   check();frame=nav._frame(current,*args,**kwargs);check();return frame
  def _action(self,current,command,expected):
   if current is not job:raise ValueError("旧卸载SOP不能执行其他任务")
   check()
   from .wechat_nav import WechatNavigator
   receipt=WechatNavigator._action(self,current,command,expected) if isinstance(nav,WechatNavigator) else nav._action(current,command,expected)
   check();return receipt
 check()
 result=(runner or old_sop)(GuardedNavigator(),job,original,understanding,platform=platform)
 check()
 if result.get("state")=="done" and (result.get("verified") is not True or job.navigation_verified is not True or getattr(job,"cancelled",False)):
  job.navigation_verified=False
  return dict(state="stopped",verified=False,reply="旧卸载SOP没有有效终态核验。")
 return result

def run(nav,j,text):
 from .agent_transport_trace import enable as enable_transport_timing
 enable_transport_timing()
 from .agent_runtime import run as execute
 from .agent_intake import understand
 from .agent_scope import build
 from .agent_capabilities import catalog
 from .remote_http import REMOTE
 from .conversation import normalize_navigation_text
 ident=getattr(j,"remote_task_id",None)
 with REMOTE.lock:
  record=REMOTE.records.get(ident)
  if not record or normalize_navigation_text(record.get("text"))!=text or record["owner"][3]!=j.device or record.get("session")!=j.session or record.get("sequence")!=j.sequence:raise ValueError("任务入口绑定失效")
  text=record["text"]
  owner=list(record["owner"]);lease=REMOTE.boots.get(j.device,{}).get("lease")
 if not lease:raise ValueError("板端租约失效")
 def publish(message):
  with REMOTE.lock:
   current=REMOTE.records.get(ident)
   if current and current["state"]=="running" and current.get("session")==j.session:
    current["reply"]=message
    REMOTE._save()
 publish("正在理解完整任务和范围，不会按应用名套固定脚本。")
 root=Path(os.environ.get("EPAPER_STATE", "state"))
 p=root/"agent-context"/(context_key(owner,text)+".json")
 context=json.loads(p.read_text()) if p.exists() else {}
 if context and context.get("original")!=text:raise ValueError("任务澄清绑定无效")
 from .agent_intake import PROMPT,validate
 today=datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
 cache_key=hashlib.sha256(json.dumps([owner,text,context.get("clarifications",[]),today,PROMPT,"text-primary-planner-v2"],ensure_ascii=False).encode()).hexdigest()
 cached=root/"agent-understanding-cache"/(cache_key+".json")
 if cached.exists():info=validate(json.loads(cached.read_text()));info["original"]=text
 else:info=understand(text,context=context.get("clarifications",[]))
 (root/"agent-runs").mkdir(mode=0o700,parents=True,exist_ok=True)
 evidence=root/"agent-runs"/(ident+"-understanding.json")
 evidence.write_text(json.dumps(info,ensure_ascii=False,indent=2));evidence.chmod(0o600)
 if info["questions"]:return dict(state="needs_input",reply="执行前需要补充："+"；".join(info["questions"]))
 publish("任务已理解，正在核对当前手机平台与真实共享画面。")
 try:nav._frame(j)
 except Exception as error:
  from .agent_doctor import RecognitionDoctor,persist_report
  RecognitionDoctor(None,task_id=ident,device=j.device,reporter=lambda report:persist_report(root,report)).assess(error,stage="attach_screen")
  raise
 session=j.screen_session
 if not session:raise ValueError("当前共享未建立")
 from .agent_existing_skills import verify_intent
 platform=getattr(j,"video_platform","android") or "android"
 from .agent_ui_context import load as load_ui_context
 info["_ui_profile"]=load_ui_context(root/"phone-ui-context.json",device=j.device,session=session,platform=platform)
 existing_platform=getattr(j,"video_platform",None) or "unknown"
 existing_request=verify_intent(text,info,existing_platform)
 record_scope=None if existing_request else build(text,context.get("clarifications",[]),info,today=datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(),journal_path=str(root/"agent-records.sqlite"))
 if not info["questions"]:
  cached.parent.mkdir(mode=0o700,parents=True,exist_ok=True);cached.write_text(json.dumps(info,ensure_ascii=False));cached.chmod(0o600)
 publish("任务已理解，正在按当前平台制订下一步。")
 granted={k for k in REGISTRY if (k in catalog(platform)["tools"] or k in ("observe","verify","stop")) and (k!="save_record" or record_scope and record_scope["allow_save"])}
 if existing_request:granted.add("uninstall_app")
 authority=Authority(ident,j.device,session,lease,frozenset(granted),time.monotonic()+540)
 def guard(a):
  nav.m._live(j)
  with REMOTE.lock:
   r=REMOTE.records.get(ident);b=REMOTE.boots.get(j.device,{})
   return bool(r and r["state"]=="running" and r["owner"]==owner and r.get("session")==j.session and r.get("sequence")==j.sequence and r.get("text")==text and REMOTE.binding_allowed(owner) and b.get("lease")==a.lease and j.screen_session==a.session and REMOTE.screen_ready(j.device))
 last_stage=[None]
 def observation(raw,hint,stage):
  if stage!=last_stage[0]:
   publish({"observe":"正在观察当前页面并规划下一步。","verify":"正在用动作后的新画面核验结果。"}.get(stage,"正在执行通用Agent任务。"));last_stage[0]=stage
  try:
   folder=root/"agent-runs"
   payload=json.dumps(dict(stage=stage,hint=hint),ensure_ascii=False).encode()
   for suffix,data in (("-current.jpg",raw),("-current-ocr.json",payload)):
    target=folder/(ident+suffix);temp=target.with_suffix(target.suffix+".tmp");temp.write_bytes(data);temp.chmod(0o600);temp.replace(target)
   archive=folder/"frames"/ident;archive.mkdir(mode=0o700,parents=True,exist_ok=True)
   number=hint.get("_observation",{}).get("frame_id","").split(":",1)[0]
   if number.isdecimal():
    stem=number.zfill(10)+"-"+stage
    for ext,data in ((".jpg",raw),(".json",payload)):
     target=archive/(stem+ext);target.write_bytes(data);target.chmod(0o600)
    for old in sorted(archive.glob("*.json"))[:-32]:
     old.with_suffix(".jpg").unlink(missing_ok=True);old.unlink(missing_ok=True)
  except OSError:pass
 j.agent_observation=observation
 doctor_model_calls=[0]
 def doctor_report(report):
  from .agent_doctor import explain
  if report["model_needed"] and report["component"]!="planner_transport" and doctor_model_calls[0]<1 and guard(authority):
   doctor_model_calls[0]+=1
   try:
    from .agent_intake import call_planner
    report["explanation"]=explain(report,model=call_planner)
   except Exception as error:report["explanation_unavailable"]=type(error).__name__
  from .agent_doctor import persist_report
  persist_report(root,report)
 j.agent_doctor_report=doctor_report
 # Owner/device-bound private learning survives immutable Agent releases.
 learning_id=context_key(owner,"navigation-experience")
 j.agent_learning_path=root/"agent-learning"/(learning_id+".json")
 j.agent_learning_scope=context_key(owner,text)
 release=Path(__file__).with_name("agent-release.json")
 version=__name__.rsplit(".agent_integration_",1)[1] if ".agent_integration_" in __name__ else getattr(j,"agent_release",None)
 if version:
  j.agent_should_yield=lambda:json.loads(release.read_text()).get("version")!=version
 # Both paths run only after understanding, a real shared frame and a fresh
 # remote owner/task/session/lease check; model capabilities are not a grant.
 if not guard(authority):raise ValueError("当前任务入口、租约或共享授权失效")
 result=try_existing_uninstall(nav,j,text,info,platform=existing_platform,authority=authority,guard=guard)
 if result is None:
  result=execute(nav,j,text,authority=authority,guard=guard,policy=policy,intake=lambda _:info,record_scope=record_scope)
 raw=getattr(j,"agent_last_frame",None)
 if isinstance(raw,bytes):
  frame=root/"agent-runs"/(ident+"-last.jpg");frame.write_bytes(raw);frame.chmod(0o600)
 output=root/"agent-runs"/(ident+"-result.json")
 output.write_text(json.dumps(result,ensure_ascii=False,indent=2));output.chmod(0o600)
 return result
