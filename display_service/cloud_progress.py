"""Public task summaries: observed facts only, no model reasoning or credentials."""
from datetime import datetime, timezone
import hashlib
LABELS={'pending':('confirmation','等待确认'),'queued':('queue','等待控制板领取'),'running':('execution','正在执行并核验'),'done':('complete','执行结束'),'error':('error','执行未完成'),'stopped':('stopped','任务已停止'),'expired':('expired','任务已过期'),'replaced':('replaced','任务已替换')}
def utc_now():return datetime.now(timezone.utc).isoformat()
def summary(task_id,source,state,verified=False,updated_at=None):
 server_cancelled=state=='stopped'
 if server_cancelled:state='stopping'
 stage,description=LABELS.get(state,('observing','等待现场状态更新'))
 if server_cancelled:stage,description='stopping','后续动作已撤销，设备停止待确认'
 verified=verified is True and state=='done'
 return dict(taskId=task_id,source=source,state=state,stage=stage,description=description,verified=verified,terminal=state in ('done','error','stopped','expired','replaced'),updatedAt=updated_at,serverCancelled=server_cancelled,stopConfirmed=False)
def job_summary(job):
 ident=getattr(job,'remote_task_id','')
 if not ident:
  raw=str(job.session)+':'+str(job.sequence)
  ident=hashlib.sha256(raw.encode()).hexdigest()[:32]
 state='stopped' if job.cancelled else job.state
 out=summary(ident,'cloud-ai' if getattr(job,'agent_job',False) else None,state,bool(job.done and state=='done' and getattr(job,'navigation_verified',False) is True))
 out['updatedAt']=None
 return out
