"""Target-region and native-OCR page anchors for animated pages."""
import re
from .skill_engine import region_matches
def build(hint):
 if not isinstance(hint,dict) or not hint.get("width") or not hint.get("height"):return None
 w,h=hint["width"],hint["height"];rows={}
 for row in hint.get("lines",[]):
  label=re.sub(r"\s+","",row["text"]);b=row["bounds"]
  if not label or len(label)>32 or re.search(r"[0-9]|屏幕共享|共享中",label):continue
  rows.setdefault(label,[]).append([(b[0]+b[2])/(2*w),(b[1]+b[3])/(2*h)])
 unique={k:v[0] for k,v in rows.items() if len(v)==1}
 return dict(width=w,height=h,anchors=dict(list(unique.items())[:32]))
def match(expected,current_raw,current_hint):
 old=expected.get("_agent_context");now=build(current_hint)
 if not old or not now or (old["width"],old["height"])!=(now["width"],now["height"]):return False
 anchors=old["anchors"];current=now["anchors"]
 shared=[k for k,p in anchors.items() if k in current and max(abs(p[i]-current[k][i]) for i in (0,1))<=.035]
 if len(shared)<8 or len(shared)/max(1,len(anchors))<.65:return False
 return isinstance(expected.get("target"),dict) and region_matches(expected["target"],current_raw)
