"""Bounded server timing only. No credentials, request bodies or actuator calls."""
import json,time,uuid,threading
_LOCK=threading.Lock()
def enable(seconds=600):
 from . import relay_http
 with _LOCK:
  original=relay_http.handle
  if getattr(original,"_phone_bounded_timing",False) is True:return
  until=time.monotonic()+min(600,max(1,seconds))
  def traced(handler,config):
   path=handler.path
   if path not in ("/app-relay/poll","/app-relay/maintenance","/app-relay/ack") or time.monotonic()>=until:return original(handler,config)
   started=time.monotonic();request=uuid.uuid4().hex[:8];operation=path.rsplit('/',1)[-1]
   print("RELAY_HTTP_TIMING "+json.dumps(dict(phase="begin",operation=operation,request=request)),flush=True)
   try:return original(handler,config)
   finally:print("RELAY_HTTP_TIMING "+json.dumps(dict(phase="end",operation=operation,request=request,elapsed_ms=round((time.monotonic()-started)*1000))),flush=True)
  traced._phone_bounded_timing=True
  relay_http.handle=traced
