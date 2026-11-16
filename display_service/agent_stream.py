"""Bounded Go SSE transport, requiring a complete terminal event."""
import json,time,urllib.request,urllib.error
class TransportError(RuntimeError):
 def __init__(self,retryable):
  super().__init__("模型连接超时或暂不可用，未重放手机输入");self.retryable=retryable
def decode(lines,deadline=None,on_usage=None):
 content=[];finish=None;usage=None;done=False;size=0
 for line in lines:
  if deadline is not None and time.monotonic()>deadline:raise TimeoutError("model total deadline")
  size+=len(line)
  if size>262144:raise ValueError("model stream too large")
  if not line.startswith(b"data:"):continue
  body=line[5:].strip()
  if body==b"[DONE]":done=True;break
  value=json.loads(body)
  if value.get("error"):raise ValueError("model stream error")
  if value.get("usage") is not None:
   usage=value["usage"]
   if on_usage:on_usage(usage)
  for row in value.get("choices",[]):
   delta=row.get("delta",{}).get("content")
   if isinstance(delta,str):content.append(delta)
   if row.get("finish_reason") is not None:finish=row["finish_reason"]
 print("AGENT_STREAM_END "+json.dumps(dict(done=done,finish=finish,chars=sum(map(len,content)),usage=usage)),flush=True)
 # An EOF without a complete stop is a failed read, never a usable plan.
 # Explicit truncation/filter/tool finishes are semantic failures, not retries.
 if finish is not None and finish!="stop":raise ValueError("model stream incomplete")
 if not done or finish is None:raise TransportError(True)
 return json.loads("".join(content)),usage
def call(payload):
 from .model_routing import vision_route,request_headers
 from .general_vision import _open_vision,_vision_url
 provider,model,cfg=vision_route()
 requested=payload.get("model")
 if requested is not None:
  allowed={m.get("id") for m in cfg.get("models",[])}
  if requested not in allowed:raise ValueError("Agent model is not configured in Go subscription")
  model=requested
 if provider!="opencode-go":raise ValueError("Agent requires Go subscription")
 payload=dict(payload,model=model,stream=True,stream_options={"include_usage":True},reasoning_effort=payload.get("reasoning_effort","none"),reasoning={"effort":payload.get("reasoning_effort","none")})
 payload.pop("thinking",None)
 req=urllib.request.Request(_vision_url(provider,cfg),data=json.dumps(payload).encode(),headers=request_headers(cfg));usage=None
 usage_box=[None]
 started=time.monotonic()
 try:
  with _open_vision(req,provider,timeout=20) as response:
   value,usage=decode(response,deadline=started+55,on_usage=lambda v:usage_box.__setitem__(0,v))
  return value
 except (OSError,urllib.error.URLError) as error:
  status=getattr(error,"code",None)
  raise TransportError(not isinstance(error,urllib.error.HTTPError) or status==429 or status is not None and status>=500) from error
 finally:
  usage=usage_box[0]
  print("VISION_USAGE "+json.dumps(dict(provider=provider,model=model,session=req.get_header("X-opencode-session"),usage=usage,transport="agent_sse",elapsed_ms=int((time.monotonic()-started)*1000)),ensure_ascii=False),flush=True)
