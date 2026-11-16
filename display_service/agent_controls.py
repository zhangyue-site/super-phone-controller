"""Frame-bound reversible brightness and literal search input. No device IO."""
import re
from .agent_gates import GateError,dialog_present
from .agent_observation import current_visual

def denied(message):raise GateError("control_evidence_required","authorization","stop",message)
def authorize(original,step,history=()):
 cap=step.get("capability")
 if cap=="type_text":
  text=step.get("text")
  if not isinstance(text,str) or not 1<=len(text)<=128 or not text.strip() or not text.isascii() or any(not 32<=ord(c)<=126 for c in text):return False
  return bool(re.search(r"搜索|查找|search",original,re.I) and text in original and not any(x.get("capability")==cap and x.get("text")==text for x in history))
 if cap=="adjust_brightness":
  value=step.get("value_percent")
  return type(value) is int and 10<=value<=90 and not any(x.get("capability")==cap and x.get("value_percent")==value for x in history) and bool(re.search(r"亮度|brightness",original,re.I)) and bool(re.search(r"(?<![0-9])"+str(value)+r"\s*[%％]",original))
 return False

def locate(step,hint,visual):
 cap=step.get("capability");allowed={"capability","target","locator","bounds"}|({"text"} if cap=="type_text" else {"value_percent"})
 if set(step)!=allowed or step.get("locator")!="icon":denied("控制工具字段或定位方式无效")
 view=current_visual(hint,visual)
 if dialog_present(hint,None):denied("当前存在待处理的授权或确认弹窗")
 if dialog_present(hint,view):
  dialogs=[r.get("bounds") for r in view.get("regions",[]) if r.get("role")=="dialog"]
  b=step.get("bounds")
  labels=" ".join(str(r.get("label","")) for r in view.get("widgets",[]))
  contained=(len(dialogs)==1 and isinstance(dialogs[0],list) and len(dialogs[0])==4 and isinstance(b,list) and len(b)==4 and dialogs[0][0]<=b[0]<b[2]<=dialogs[0][2] and dialogs[0][1]<=b[1]<b[3]<=dialogs[0][3])
  if cap!="adjust_brightness" or not contained or re.search(r"授权|权限|允许|同意|确认|删除|支付|登录|permission|allow|consent|confirm|sign.?in",labels,re.I):denied("当前前景层不是可直接操作的亮度控件面板")
 target=step.get("target");bounds=step.get("bounds")
 rows=[x for x in view.get("widgets",[]) if x.get("label")==target and x.get("bounds")==bounds]
 if len(rows)!=1:denied("控制目标必须唯一匹配当前真实图像")
 row=rows[0];w,h=hint["width"],hint["height"]
 if not isinstance(bounds,list) or len(bounds)!=4 or any(type(v) is not int for v in bounds) or not 0<=bounds[0]<bounds[2]<=w or not 0<=bounds[1]<bounds[3]<=h:denied("控制区域无效")
 if cap=="type_text":
  text=step.get("text")
  if row.get("role")!="search_input" or row.get("focused") is not True or row.get("password") is not False:denied("需要当前已聚焦的非密码搜索框")
  if not isinstance(text,str) or not 1<=len(text)<=128 or not text.strip() or not text.isascii() or any(not 32<=ord(c)<=126 for c in text):denied("当前工具仅接通可打印ASCII搜索文字")
  try:sequence=int(hint["_observation"]["frame_id"].split(":",1)[0])
  except (KeyError,TypeError,ValueError):denied("搜索输入缺少真实帧序号")
  if sequence<1:denied("搜索输入帧序号无效")
  return dict(op="hid_text",text=text,target=dict(purpose="visible_search",role="search",visible=True,focused=True,password=False,frame=sequence)),bounds
 if cap!="adjust_brightness" or row.get("role")!="brightness_slider":denied("需要明确识别的亮度滑条")
 if re.search(r"音量|耳机|扬声器|volume|headphone|speaker",str(target),re.I):denied("音量控件不能使用亮度工具")
 value=step.get("value_percent")
 if type(value) is not int or not 10<=value<=90:denied("亮度验收范围为10%至90%")
 x1,y1,x2,y2=bounds;dx,dy=x2-x1,y2-y1
 if dx>=2*dy:x=x1+dx*value/100;y=(y1+y2)/2
 elif dy>=2*dx:x=(x1+x2)/2;y=y2-dy*value/100
 else:denied("亮度滑条方向不明确")
 current=row.get("observed_percent")
 if type(current)not in (int,float)or not 0<=current<=100 or row.get("observed_source")!="current_jpeg_pixel_boundary":denied("缺少本帧滑条填充边界，不能猜测拖动起点")
 if dx>=2*dy:sx=x1+dx*current/100;sy=(y1+y2)/2
 else:sx=(x1+x2)/2;sy=y2-dy*current/100
 return dict(op="hid_pointer",kind="drag",x=round(sx*32767/w),y=round(sy*32767/h),x2=round(x*32767/w),y2=round(y*32767/h),duration_ms=500),bounds

def same_command(current,planned):
 # Frame identity advances on the final fresh read; only that field may change.
 if current.get("op")!="hid_text":return current==planned
 a=dict(current,target={k:v for k,v in current["target"].items() if k!="frame"});b=dict(planned,target={k:v for k,v in planned["target"].items() if k!="frame"})
 return a==b

def locate_edge(step,hint,visual=None):
 allowed={'capability','target','locator','bounds','edge','anchor_percent','distance_percent'}
 if not isinstance(step,dict) or set(step)!=allowed or step.get('locator')!='edge' or step.get('bounds')is not None:denied('边缘手势字段无效；起止点由当前几何生成')
 if not isinstance(step.get('target'),str) or not 1<=len(step['target'])<=80:denied('边缘手势目标无效')
 from .agent_runtime import DENY,NAV_SENSITIVE
 from .agent_gates import permission_approval
 if DENY.search(step['target']) or NAV_SENSITIVE.search(step['target']) or permission_approval(step['target']):denied('边缘手势不能绕过受限目标规则')
 edge=step['edge'];anchor=step['anchor_percent'];distance=step['distance_percent'];w,h=hint['width'],hint['height']
 if edge not in ('top','bottom','left','right') or type(anchor)is not int or not 5<=anchor<=95 or type(distance)is not int or not 20<=distance<=80:denied('边缘或比例超出可审查范围')
 if dialog_present(hint,None):denied('当前存在需要先处理的确认或授权弹窗')
 if edge in ('top','bottom'):
  x=w*anchor//100;y=1 if edge=='top'else h-2;end=[x,h*distance//100 if edge=='top'else h*(100-distance)//100];direction='down'if edge=='top'else'up'
 else:
  x=1 if edge=='left'else w-2;y=h*anchor//100;end=[w*distance//100 if edge=='left'else w*(100-distance)//100,y];direction='right'if edge=='left'else'left'
 bounds=[max(0,x-2),max(0,y-2),min(w,x+3),min(h,y+3)]
 from .sop_runtime import command
 return command(dict(sop='page',end=end,direction=direction),bounds,w,h),bounds
