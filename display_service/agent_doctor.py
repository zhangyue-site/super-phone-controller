"""Recognition-pipeline diagnostics. No actuator, shell or authority provider."""
import collections,json,time
from .agent_contract import Authority
from .agent_observation import Snapshot,_authority_matches
from .agent_gates import GateError

class RecognitionDoctor:
 def __init__(self,authority,*,clock=time.monotonic,reporter=None,max_repeats=3,task_id=None,device=None):
  if authority is not None and not isinstance(authority,Authority):raise ValueError("doctor authority type")
  if authority is None and not all(isinstance(v,str) and v for v in (task_id,device)):raise ValueError("doctor requires trusted task context")
  self.task_id=authority.goal_id if authority else task_id;self.device=authority.device if authority else device;self.session=authority.session if authority else None
  self.authority=authority;self.clock=clock;self.reporter=reporter;self.counts=collections.Counter();self.max_repeats=max_repeats
 def assess(self,error,*,snapshot=None,pending=False,input_sent=False,stage="observation"):
  code=error.code if isinstance(error,GateError) else "pipeline_error"
  message=str(error)
  if not isinstance(error,GateError):
   if "锁屏" in message:code="screen_locked"
   elif "没有收到新的" in message or "没有新的" in message:code="frame_unavailable"
   elif isinstance(error,TimeoutError) or "Transport" in type(error).__name__:code="model_transport"
  observed=None
  if snapshot is not None:
   if self.authority is None or not isinstance(snapshot,Snapshot) or not _authority_matches(snapshot.identity(),self.authority):code="doctor_binding_changed"
   else:
    hint=snapshot.hint();labels=collections.Counter(row["text"] for row in hint["lines"])
    observed=dict(frame_id=snapshot.identity()["frame_id"],width=hint["width"],height=hint["height"],age_ms=round(max(0,self.clock()-snapshot.observed_at)*1000),ocr_source=hint.get("source","unknown"),ocr_rows=len(hint["lines"]),duplicate_labels=sum(n>1 for n in labels.values()))
  self.counts[code]+=1;repeat=self.counts[code]
  component="pipeline";recovery="inspect_pipeline";reason="识别链路出现未分类问题，保留证据排查。"
  if code.startswith("visual_") or code.startswith("gesture_") or code in ("frame_changed","planner_needs_observation"):component="visual_locator";recovery="refresh_visual";reason="旧图像定位与当前画面不一致，需要重新观察定位。"
  elif code.startswith("ocr_") or code=="locator_not_unique":component="ocr_locator";recovery="refresh_observation";reason="当前OCR没有唯一且可追溯的目标，需要新帧或图像补充。"
  elif code in ("observation_stale","frame_unavailable"):component="capture";recovery="refresh_observation";reason="当前画面缺失或过期，先恢复真实新帧。"
  elif code=="screen_locked":component="capture";recovery="user_unlock";reason="手机已锁屏，需要本人解锁后恢复真实画面。"
  elif code=="model_transport":component="planner_transport";recovery="retry_read_only";reason="模型连接未完成，只允许重新读取规划，不重放输入。"
  elif code in ("authority_denied","observation_binding_changed","doctor_binding_changed"):component="authorization";recovery="stop";reason="当前任务或共享绑定失效，不能沿用旧授权。"
  elif code=="dialog_requires_resolution":component="foreground_dialog";recovery="return_to_planner";reason="先由主Agent核查当前弹窗及获授权的退出方式。"
  if repeat>self.max_repeats and recovery in ("refresh_visual","refresh_observation","retry_read_only"):recovery="inspect_pipeline";reason="同类失败反复出现，需要诊断链路，避免继续空跑。"
  if pending or input_sent:component="input_outcome";recovery="reconcile_original";reason="已有待核查输入或写入，只核查原结果，不重新输入。"
  report=dict(schema=1,task_id=self.task_id,device=self.device,session=self.session,stage=stage,code=code,component=component,reason=reason,recovery=recovery,repeat=repeat,observation=observed,input_allowed=False,retry_input=False,requires_user=recovery=="user_unlock",model_needed=recovery=="inspect_pipeline")
  if self.reporter:
   try:self.reporter(report)
   except OSError:pass
  print("AGENT_DOCTOR "+json.dumps({k:report[k] for k in ("task_id","component","code","recovery","repeat")},ensure_ascii=False),flush=True)
  return report

def explain(report,*,model):
 """Optional text-only diagnosis. Recommendations never become executable commands."""
 payload=dict(max_tokens=1024,reasoning_effort="none",temperature=0,response_format={"type":"json_object"},messages=[dict(role="system",content="你是手机识别链路Doctor，只解释结构化诊断。返回JSON summary字符串、likely_causes字符串数组、checks字符串数组。不能返回shell、动作、坐标、授权决定或声称已修复。未知写入只能核查原结果，不得重放。"),dict(role="user",content=json.dumps(report,ensure_ascii=False))])
 result=model(payload)
 if not isinstance(result,dict) or set(result)!={"summary","likely_causes","checks"} or not isinstance(result["summary"],str) or any(not isinstance(result[k],list) or len(result[k])>8 or any(not isinstance(v,str) or len(v)>300 for v in result[k]) for k in ("likely_causes","checks")):raise ValueError("doctor model must only explain diagnostic facts")
 return result

def persist_report(state_root,report):
 from pathlib import Path
 import re
 ident=report.get("task_id")
 if not isinstance(ident,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}",ident):raise ValueError("doctor report task identity")
 folder=Path(state_root)/"agent-doctor";folder.mkdir(mode=0o700,parents=True,exist_ok=True)
 target=folder/(ident+".json");temp=target.with_suffix(".tmp")
 temp.write_text(json.dumps(report,ensure_ascii=False,indent=2));temp.chmod(0o600);temp.replace(target)


def require_observation_recovery(report):
 if (report.get("code")=="gesture_invalid" and report.get("repeat",0)>=3
     and report.get("recovery")!="reconcile_original"):
  raise GateError("planner_geometry_blocked","observation","stop","连续三次手势区域或路径无效，已停止；未裁剪坐标或重放输入，请重新定位。")
 if report.get("code")=="visual_app_scope_mismatch" and report.get("repeat",0)>=3:
  raise GateError("planner_scope_blocked","observation","stop","连续三次候选应用不匹配本次目标，已停止，无输入；需要纠正视觉分类，不继续空转。")
 """Bound failed source-stability waits; never authorize or replay input."""
 if (isinstance(report,dict) and report.get("code")=="target_not_stable"
     and type(report.get("repeat")) is int and report["repeat"]>=3
     and report.get("recovery")!="reconcile_original"):
  raise GateError("observation_pipeline_blocked","observation","stop",
      "目标连续3轮未取得10个稳定新源帧；已停止本任务，请检查本地采样频率、帧间隔和共享绑定。此步骤未发送新的输入。")
