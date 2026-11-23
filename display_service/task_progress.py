"""Read-only, evidence-based progress. No task dispatch or authorization changes."""
import time
PHASES=frozenset(('recognizing','dispatching','operating','verifying','awaiting_frame','recognized'))
def mark_progress(job,phase):
 if phase not in PHASES or job.done or job.cancelled:return
 if phase=='recognized':
  job.task_completed=getattr(job,'task_completed',7)|8
  return
 previous=getattr(job,'task_phase','')
 if phase=='recognizing' and previous not in ('recognizing','verifying'):
  job.task_round=getattr(job,'task_round',0)+1
  job.task_completed=7
 job.task_phase=phase
 if phase=='operating':job.task_completed=getattr(job,'task_completed',7)|16
 elif phase=='awaiting_frame':job.task_completed=getattr(job,'task_completed',7)|32
 job.task_progress_at=time.monotonic()
def task_progress(record,job):
 state=record.get('state');bits=0;phase='unknown';round_=0
 if state=='pending':phase='confirming';bits=3
 elif state=='queued':phase='queued';bits=7
 elif state=='running':
  bits=7
  if job is not None:
   phase=getattr(job,'task_phase','unknown');round_=getattr(job,'task_round',0)
   bits=getattr(job,'task_completed',7)
   if phase=='awaiting_frame':phase='unknown'
 elif state=='done':
  phase='done' if record.get('verified') is True else 'error'
  # Only verification and task completion are certified by this result.
  bits=(getattr(job,'task_completed',0)|199) if phase=='done' else getattr(job,'task_completed',0)
 elif state in ('stopped','cancelled'):phase='stopped'
 elif state in ('error','expired','replaced'):phase='error'
 return {'phase':phase,'round':round_,'completed':bits}
