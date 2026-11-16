"""Generic action/effect ledger and source provenance. No app-specific scripts."""
import hashlib,io,re,unicodedata
from PIL import Image

class SourceUnverified(ValueError):
 def __init__(self,terminal=False):
  super().__init__('目标应用身份缺少本任务的真实命名入口轨迹和新界面证据；不能把当前日期归到目标App')
  self.terminal=terminal

def key(value):return re.sub(r'\s+','',unicodedata.normalize('NFKC',str(value))).lower()
def app_matches(a,b):
 a,b=key(a),key(b)
 aliases=lambda s:{s,s[:-2]} if s.endswith('视频') and len(s)>2 else {s}
 return bool(aliases(a)&aliases(b))
def body_hash(raw):
 try:
  with Image.open(io.BytesIO(raw))as image:
   w,h=image.size;return hashlib.sha256(image.convert('RGB').crop((0,int(h*.075),w,int(h*.98))).tobytes()).hexdigest()
 except (OSError,ValueError):return hashlib.sha256(raw).hexdigest()

def roi_hash(raw,bounds):
 if not isinstance(bounds,list)or len(bounds)!=4:return body_hash(raw)
 try:
  with Image.open(io.BytesIO(raw))as image:return hashlib.sha256(image.convert("RGB").crop(tuple(bounds)).tobytes()).hexdigest()
 except(OSError,ValueError):return hashlib.sha256(raw).hexdigest()

def text_visible(hint,label,bounds=None):
 hits=[r for r in hint.get('lines',[]) if key(r.get('text'))==key(label)]
 if bounds is None:return len(hits)==1
 return any(max(abs(a-b)for a,b in zip(r['bounds'],bounds))<=3 for r in hits)

def page_effect(before,after,bounds,direction):
 if not isinstance(bounds,list) or len(bounds)!=4:return None
 x1,y1,x2,y2=bounds
 def anchors(hint):
  values={}
  for row in hint.get("lines",[]):
   a,b,c,d=row["bounds"];point=((a+c)/2,(b+d)/2)
   if x1<=point[0]<=x2 and y1<=point[1]<=y2 and b>=hint.get("height",1)*.075:values.setdefault(key(row["text"]),[]).append(point)
  return {label:points[0]for label,points in values.items()if len(points)==1}
 old,new=anchors(before),anchors(after)
 if len(old)>=4 and len(new)>=4:
  shared=set(old)&set(new)
  if len(set(old)-shared)>=2 and len(set(new)-shared)>=2 and len(shared)/min(len(old),len(new))<=.5:return "container_content_replaced"
 axis=0 if direction in ("left","right")else 1
 sign=-1 if direction in ("left","up")else 1
 threshold=max(12,((x2-x1)if axis==0 else(y2-y1))*.03)
 moved=[label for label in set(old)&set(new)if (new[label][axis]-old[label][axis])*sign>=threshold]
 return "directional_ocr_motion" if len(moved)>=2 else None

def app_grid(hint):
 w,h=hint.get("width",1),hint.get("height",1);rows=[]
 for row in hint.get("lines",[]):
  x1,y1,x2,y2=row["bounds"]
  if not h*.13<=(y1+y2)/2<=h*.85 or x2-x1>w*.32 or y2-y1>h*.045 or len(key(row["text"]))>24:continue
  point=((x1+x2)/2,(y1+y2)/2)
  bucket=next((group for group in rows if abs(group[0][1]-point[1])<=h*.02),None)
  if bucket is None:rows.append([point])
  else:bucket.append(point)
 regular=[]
 for group in rows:
  xs=sorted(p[0]for p in group);unique=[]
  for x in xs:
   if not unique or x-unique[-1]>=w*.15:unique.append(x)
  if len(unique)>=3:regular.append((group[0][1],unique))
 return any(abs(a[0]-b[0])>=h*.06 and sum(any(abs(x-y)<=w*.06 for y in b[1])for x in a[1])>=3 for i,a in enumerate(regular)for b in regular[i+1:])

class Cycle:
 NAV={'home','back','open_app','tap_text','tap_icon','page','dismiss','edge_swipe'}
 EXPECTED={'home':'launcher_visible','back':'previous_page_or_overlay_closed','open_app':'named_app_entered','tap_text':'target_effect_visible','tap_icon':'target_effect_visible','page':'visible_container_changed','dismiss':'overlay_closed','edge_swipe':'system_surface_changed'}
 def __init__(self,expected_app=None):
  self.expected_app=expected_app;self.source_verified=not bool(expected_app);self.source_basis='not_required' if not expected_app else 'unknown'
  self.pending=None;self.entry=None;self.events=[];self.repeats={};self.source_attempts=0;self.last_check=None
 def record(self,event,**fields):
  self.events.append(dict(event=event,**fields));self.events=self.events[-64:]
 def contract(self):
  return dict(expected_app=self.expected_app,source_verified=self.source_verified,source_basis=self.source_basis,last_check=self.last_check,pending_action=None if self.pending is None else dict(capability=self.pending['capability'],target=self.pending['target'],expected=self.EXPECTED.get(self.pending['capability'],'tool_result'),before_labels=[r['text']for r in self.pending.get('before_hint',{}).get('lines',[])[:12]]))
 def observe(self,raw,hint):
  if not self.expected_app:return
  # A brand/name may also be a launcher icon or advertisement; it alone is not provenance.
  if self.entry and self.source_verified and text_visible(hint,self.entry['target'],self.entry.get('bounds')):
   self.source_verified=False;self.source_basis='returned_to_entry_surface'
  if self.entry and self.entry['receipt']=='confirmed' and body_hash(raw)!=self.entry['before']:
   if len(hint.get('lines',[]))>=4 and not text_visible(hint,self.entry['target'],self.entry.get('bounds')):
    self.source_verified=True;self.source_basis='confirmed_named_entry';self.record('source_verified',basis=self.source_basis,app=self.expected_app)
 def require_source(self):
  if self.source_verified:return
  self.source_attempts+=1;self.record('source_rejected',attempt=self.source_attempts)
  raise SourceUnverified(self.source_attempts>=3)
 def plan(self,step,raw,hint,bounds=None):
  cap=step.get('capability');target=step.get('target','')
  self.pending=dict(capability=cap,target=target,before=body_hash(raw),bounds=bounds,receipt='pending',before_hint=hint,direction=step.get('direction'),before_roi=roi_hash(raw,bounds))
  self.record('plan',capability=cap,target=target,expected=self.EXPECTED.get(cap,'tool_result'))
  if cap=='home':self.source_verified=not bool(self.expected_app);self.source_basis='unknown';self.entry=None
  if cap=='open_app':
   self.source_verified=not bool(self.expected_app);self.source_basis='unknown';self.entry=None
   if self.expected_app and app_matches(target,self.expected_app):self.entry=self.pending.copy()
 def receipt(self,state):
  if self.pending:self.pending['receipt']=state
  if self.entry:self.entry['receipt']=state
  self.record('receipt',state=state)
 def check(self,raw,hint,decision):
  self.observe(raw,hint)
  pending=self.pending;self.pending=None
  if pending is None:return dict(state='observation',effect_verified=None)
  if pending['receipt']!='confirmed':
   self.last_check=dict(state='outcome_unknown',effect_verified=False,retry_input=False);self.record('check',**self.last_check);return self.last_check
  cap=pending['capability'];changed=body_hash(raw)!=pending['before']
  model_ok=decision.get('step_verified')is True or decision.get('done')is True
  roi_changed=roi_hash(raw,pending.get('bounds'))!=pending['before_roi']
  mechanical=page_effect(pending['before_hint'],hint,pending.get('bounds'),pending.get('direction')) if cap=='page' and changed and roi_changed else None
  if cap=='home' and changed and app_grid(hint):mechanical='launcher_grid_after_home'
  if cap=='open_app' and changed and roi_changed and len(hint.get('lines',[]))>=4 and not text_visible(hint,pending['target'],pending.get('bounds')):mechanical='application_surface_changed'
  verified=(model_ok or mechanical is not None) and (changed or cap not in self.NAV)
  state='effect_verified' if verified else 'effect_unverified'
  repeat=0
  if verified:self.repeats.pop((cap,key(pending['target'])),None)
  if not verified:
   ident=(cap,key(pending['target']));repeat=self.repeats.get(ident,0)+1;self.repeats[ident]=repeat
  self.last_check=dict(state=state,effect_verified=verified,effect_basis=mechanical or ('model_and_frame'if verified else 'not_verified'),model_step_verified=decision.get('step_verified','missing'),model_done=decision.get('done'),visual_changed=changed,roi_changed=roi_changed,repeat=repeat,stop=repeat>=2)
  self.record('check',**self.last_check);return self.last_check
