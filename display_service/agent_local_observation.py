"""Bounded observation-only wait; no model, HID, or authority creation."""
import time,uuid,re,json
from .local_observation import ready_region,ready_observation
class TargetNotStable(ValueError):pass

class _FailureTrace:
 def __init__(self,ident,bounds):
  self.ident=ident;self.bounds=list(bounds);self.rows=[];self.first_scope=None
  self.scope_changed=False;self.request_seen=False;self.consecutive_source_gap=False;self.transport_gap_only=False;self.counter_reset=False
 def sample(self,hint,frame_seq):
  local=hint.get('local_observation')
  if not isinstance(local,dict):return
  scope=local.get('scopeHash')
  if self.first_scope is None:self.first_scope=scope
  elif scope!=self.first_scope:self.scope_changed=True
  region=next((v for v in local.get('regions',[]) if isinstance(v,dict) and v.get('id')==self.ident),None)
  row={'frame_sequence':frame_seq,'request_region_seen':region is not None}
  for key in ('sourceSequence','sourceTimestampNs','ageMs'):
   if type(local.get(key))is int:row[key]=local[key]
  if region is not None:
   self.request_seen=True
   for key in ('count','stableMs'):
    if type(region.get(key))is int:row[key]=region[key]
   row['bounds_match']=region.get('bounds')==self.bounds
   row['ready_reported']=region.get('ready')is True
  if self.rows:
   prev=self.rows[-1];ds=row.get('sourceSequence',0)-prev.get('sourceSequence',0);dt=row.get('sourceTimestampNs',0)-prev.get('sourceTimestampNs',0)
   if ds==1 and dt>250_000_000:self.consecutive_source_gap=True
   elif ds>1 and dt>250_000_000:self.transport_gap_only=True
   if ds>0 and 'count'in row and 'count'in prev and (row['count']<prev['count'] or row.get('stableMs',0)<prev.get('stableMs',0)):self.counter_reset=True
  if self.rows and self.rows[-1]==row:return
  self.rows.append(row);self.rows=self.rows[-32:]
 def emit(self,job,reason):
  report=dict(reason=reason,bounds=self.bounds,request_region_observed=self.request_seen,
   request_delivery='observed' if self.request_seen else 'unknown_not_observed',scope_change_observed=self.scope_changed,
   consecutive_source_gap_observed=self.consecutive_source_gap,transport_snapshot_gap_observed=self.transport_gap_only,
   target_counter_reset_observed=self.counter_reset,target_hash_change='unknown_not_reported',samples=self.rows[-8:])
  records=getattr(job,'agent_local_stability_failures',[]);job.agent_local_stability_failures=(records+[report])[-32:]
  print('LOCAL_STABILITY_PENDING '+json.dumps(report,ensure_ascii=False,allow_nan=False),flush=True)

def wait_for_target(job,raw,seq,sig,hint,bounds,label,*,read,guard,clock=time.monotonic,request_id=lambda:uuid.uuid4().hex,budget=8.0):
 guard()
 if not isinstance(hint.get('local_observation'),dict) and not getattr(job,'local_observation_capable',False):return raw,seq,sig,hint
 def record_ready(region):
  records=getattr(job,'agent_local_stability',[])
  records.append(dict(region,frame_id=(hint.get('_observation')or{}).get('frame_id')))
  job.agent_local_stability=records[-32:]
 region=ready_observation(hint,bounds,label=label)
 if region is not None:
  record_ready(region);return raw,seq,sig,hint
 barrier=getattr(job,'video_barrier',None)
 if not isinstance(barrier,str) or not re.fullmatch('[a-f0-9]{32}',barrier) or barrier=='0'*32:raise TargetNotStable('本地观察缺少当前共享任务')
 ident='req-'+request_id();w,h=hint['width'],hint['height']
 required_frames=(hint.get("local_observation")or{}).get("requiredFrames",10)
 if type(required_frames)is not int or required_frames not in (4,10):raise TargetNotStable("本地观察帧门槛协议不受支持")
 request=dict(barrier=barrier,width=w,height=h,requiredFrames=required_frames,regions=[dict(id=ident,label=label[:160],bounds=list(bounds))])
 job.local_observation_request=request;began=clock();trace=_FailureTrace(ident,bounds);reason="stability_budget_exhausted"
 try:
  for _ in range(32):
   guard()
   trace.sample(hint,seq)
   if getattr(job,'video_barrier',None)!=barrier:
    reason='task_scope_changed';raise TargetNotStable('共享任务已经改变')
   region=ready_observation(hint,bounds,region_id=ident)
   if region is not None:
    record_ready(region);return raw,seq,sig,hint
   if clock()-began>=budget:break
   raw,newseq,sig,hint=read(seq)
   if type(newseq)is not int or newseq<=seq:
    reason='no_new_transport_frame';raise TargetNotStable('没有新的共享帧')
   seq=newseq
   if (hint.get('width'),hint.get('height'))!=(w,h):
    trace.sample(hint,seq);reason='geometry_changed';raise TargetNotStable('观察几何已经改变')
  trace.sample(hint,seq)
  raise TargetNotStable('目标区域尚未达到10个连续新源帧且稳定600毫秒；本轮未发送输入')
 except TargetNotStable:
  try:trace.emit(job,reason)
  except Exception:pass
  raise
 finally:
  if getattr(job,'local_observation_request',None)is request:job.local_observation_request=None
