"""Conservative page-gesture binding: fixed actual origin, stable corridor, page anchors.
No model/HID calls. Dynamic pixels OUTSIDE the gesture corridor are allowed.
"""
import io,re
from PIL import Image
from .agent_gates import GateError,dialog_present,permission_approval
from .agent_observation import current_visual,rebind_visual_region
from .sop_runtime import command

RESTRICTED=re.compile(r"付款|支付|购买|充值|删除|清空|授权|权限|登录|卸载|安装|同意|允许|提交|发送|重置|确认",re.I)

def reject(code,message):raise GateError(code,'observation','reobserve',message)
def intersects(a,b):return a[0]<b[2] and b[0]<a[2] and a[1]<b[3] and b[1]<a[3]
def contains(a,b):return a[0]<=b[0]<b[2]<=a[2] and a[1]<=b[1]<b[3]<=a[3]

def geometry(step,hint):
 if step.get('capability')!='page':reject('gesture_invalid','只接受已登记翻页动作')
 w,h=hint['width'],hint['height'];b=step.get('bounds');direction=step.get('direction')
 if not isinstance(b,list) or len(b)!=4 or any(type(v)is not int for v in b) or not 0<=b[0]<b[2]<=w or not 0<=b[1]<b[3]<=h:reject('gesture_invalid','手势区域无效')
 end=step.get('end')
 if end is None:
  x1,y1,x2,y2=b
  if direction in ('left','right') and x2-x1>=w*.25:
   start=(x1+int((x2-x1)*(.8 if direction=='left' else .2)),(y1+y2)//2);end=[x1+int((x2-x1)*(.2 if direction=='left' else .8)),start[1]]
  elif direction in ('up','down') and y2-y1>=h*.25:
   start=((x1+x2)//2,y1+int((y2-y1)*(.8 if direction=='up' else .2)));end=[start[0],y1+int((y2-y1)*(.2 if direction=='up' else .8))]
  else:reject('gesture_invalid','手势方向或容器尺寸无效')
  origin=[max(0,start[0]-3),max(0,start[1]-3),min(w,start[0]+3),min(h,start[1]+3)]
 else:origin=list(b);start=((b[0]+b[2])/2,(b[1]+b[3])/2)
 if not isinstance(end,list) or len(end)!=2 or any(type(v)is not int for v in end) or not 0<=end[0]<w or not 0<=end[1]<h:reject('gesture_invalid','手势终点无效')
 if start[0]!=end[0] and start[1]!=end[1]:reject('gesture_path_unsupported','未证明斜向手势路径，重新规划')
 pad=max(6,round(min(w,h)*.02))
 corridor=[max(0,int(min(start[0],end[0]))-pad),max(0,int(min(start[1],end[1]))-pad),min(w,int(max(start[0],end[0]))+pad+1),min(h,int(max(start[1],end[1]))+pad+1)]
 expected=command(dict(step,sop='page',end=end),origin,w,h)
 return origin,corridor,expected

def checked_container(step,hint,visual):
 view=current_visual(hint,visual);origin,path,expected=geometry(step,hint)
 if dialog_present(hint,view):reject('gesture_occluded','前景弹窗阻断手势路径')
 containers=[r for r in view.get('regions',[]) if r.get('role')in('scroll_container','blank_gesture_area') and contains(r['bounds'],path)]
 exact=[r for r in containers if r['bounds']==step['bounds']]
 if len(exact)==1:containers=exact
 if len(containers)!=1:reject('gesture_container_ambiguous','当前手势容器未唯一定位')
 container=containers[0]
 for row in view.get('widgets',[]):
  role=row.get('role');box=row['bounds']
  if role!='text' and intersects(box,origin):reject('gesture_origin_control','手势起点覆盖控件，请重新规划')
  if role in ('brightness_slider','volume_slider','search_input','button','tab','back','close') and intersects(box,path):reject('gesture_path_control','手势路径穿过受限或独立交互控件')
 for row in hint.get('lines',[]):
  if (RESTRICTED.search(row['text']) or permission_approval(row['text'])) and intersects(row['bounds'],path):reject('gesture_path_restricted','手势路径覆盖受限文字控件')
 return container,origin,path,expected

def _anchors(hint,container):
 rows={}
 for row in hint.get('lines',[]):
  b=row['bounds']
  if contains(container,b):rows.setdefault(row['text'],[]).append(b)
 return {s:b[0] for s,b in rows.items() if len(b)==1}

def rebind_gesture(visual,old,new,before,after,step,planned_command):
 old_hint,new_hint=old.hint(),new.hint()
 container,origin,path,expected=checked_container(step,old_hint,visual)
 if expected!=planned_command:reject('gesture_command_mismatch','实际HID起点或终点与手势证据不一致')
 # Existing same-session/hash/geometry checks and exact origin pixels stay mandatory.
 rebound=rebind_visual_region(visual,old,new,before,after,origin)
 current,latest_origin,latest_path,current_command=checked_container(step,new_hint,rebound)
 if (container!=current or origin!=latest_origin or path!=latest_path or current_command!=planned_command):reject('gesture_geometry_changed','手势容器或发送坐标改变')
 anchor_bounds=[0,0,old_hint['width'],old_hint['height']] if container['role']=='blank_gesture_area' else container['bounds']
 a,b=_anchors(old_hint,anchor_bounds),_anchors(new_hint,anchor_bounds)
 w,h=old_hint['width'],old_hint['height'];tol=max(2,round(min(w,h)*.005))
 shared=[box for label,box in a.items() if label in b and max(abs(x-y) for x,y in zip(box,b[label]))<=tol]
 cb=anchor_bounds
 if len(shared)<3 or max(v[2] for v in shared)-min(v[0] for v in shared)<(cb[2]-cb[0])*.25 or max(v[3] for v in shared)-min(v[1] for v in shared)<(cb[3]-cb[1])*.25:
  reject('gesture_context_changed','容器缺少分布稳定的独立页面锚点')
 try:
  with Image.open(io.BytesIO(before)) as left,Image.open(io.BytesIO(after)) as right:
   equal=left.size==right.size==(w,h) and left.convert('RGB').crop(tuple(path)).tobytes()==right.convert('RGB').crop(tuple(path)).tobytes()
 except (ValueError,OSError):equal=False
 if not equal:reject('gesture_path_changed','当前手势走廊像素发生变化，未证明无新遮挡')
 # Preserve relevant widgets too; future final-frame checks must still see obstacles.
 from .agent_observation import bind_visual
 return bind_visual(new,dict(scene=visual['scene'],widgets=visual['widgets'],regions=[container]))
