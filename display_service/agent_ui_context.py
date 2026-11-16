"""Compact trusted OEM priors bound to one current capture, never an actuator."""
import hashlib,json,math,time
from pathlib import Path

def load(path,*,device,session,platform,now=None):
 now=time.time()if now is None else now
 try:
  path=Path(path)
  if not isinstance(session,str) or not session or path.stat().st_size>16384:return None
  value=json.loads(path.read_text())
  if not isinstance(value,dict) or value.get('v')!=1:return None
  records=value.get('bindings')
  if not isinstance(records,list) or len(records)>16:return None
  for r in records:
   if not isinstance(r,dict) or (r.get('device'),r.get('capture_sha256'),r.get('platform'))!=(device,hashlib.sha256(session.encode()).hexdigest(),platform):continue
   issued,expires=r.get('issued_at'),r.get('expires_at')
   if any(type(t)not in(int,float)or not math.isfinite(t)for t in [issued,expires]) or not issued<=now<expires<=issued+3600:continue
   hint=r.get('hint');sources=r.get('sources')
   if not isinstance(hint,str)or not 1<=len(hint)<=640 or not isinstance(sources,list)or len(sources)>5 or any(not isinstance(url,str)or not url.startswith('https://')or len(url)>512 for url in sources):continue
   fields={k:r[k]for k in ['manufacturer','model','system','android_release','panel_style','hint','sources']if k in r}
   return dict(fields,binding='current_capture_only',basis='authorized_device_diagnostics_and_official_docs')
 except (OSError,ValueError,TypeError,KeyError):pass
 return None
