"""Optional, untrusted UI observations bound to an authenticated image frame.
No phone actions or inference providers live here. Screenshots remain evidence.
"""
import base64, copy, hashlib, io, json, re
from PIL import Image
CONTENT_TYPE='application/vnd.pcflash.screen+json'
MAX_ENVELOPE=786432

def decode_frame(kind,raw,native_width,native_height):
 if kind=='image/jpeg':return raw,None
 if kind!=CONTENT_TYPE:raise ValueError('capture content type')
 obj=json.loads(raw)
 if not isinstance(obj,dict) or set(obj)!={'jpegBase64','accessibility'}:raise ValueError('frame envelope')
 if not isinstance(obj['jpegBase64'],str):raise ValueError('frame image')
 image=base64.b64decode(obj['jpegBase64'],validate=True)
 if not 0<len(image)<=524288:raise ValueError('image size')
 try:
  with Image.open(io.BytesIO(image)) as im:
   w,h=im.size
   if im.format!='JPEG' or not 1<=w<=4096 or not 1<=h<=4096 or w*h>4194304:raise ValueError('frame dimensions')
 except Image.DecompressionBombError as e:raise ValueError('frame dimensions') from e
 return image,validate_tree(obj['accessibility'],native_width,native_height,w,h)

def validate_tree(obj,native_width,native_height,width,height):
 try:
  if not isinstance(obj,dict) or set(obj)!={'version','width','height','ageMs','stableForMs','package','nodes'}:return None
  nw,nh=obj['width'],obj['height']
  if any(type(x) is not int for x in (nw,nh,native_width,native_height,width,height)):return None
  if not 100<=nw<=10000 or not 100<=nh<=10000 or (nw,nh)!=(native_width,native_height):return None
  if abs(width*nh-height*nw)>max(nw,nh):return None
  if obj['version']!=1 or type(obj['version']) is not int:return None
  if type(obj['ageMs']) is not int or not 0<=obj['ageMs']<=400:return None
  if type(obj['stableForMs']) is not int or not 150<=obj['stableForMs']<=3600000:return None
  if not isinstance(obj['package'],str) or not re.fullmatch(r'[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+',obj['package']):return None
  nodes=obj['nodes']
  if not isinstance(nodes,list) or not 1<=len(nodes)<=192:return None
  if len(json.dumps(obj,ensure_ascii=False).encode())>65536:return None
  clean=[]
  for n in nodes:
   if not isinstance(n,dict) or set(n)!={'text','description','bounds','clickable','editable'}:return None
   if any(not isinstance(n[k],str) or len(n[k])>160 for k in ('text','description')):return None
   if not n['text'] and not n['description']:continue
   if any(type(n[k]) is not bool for k in ('clickable','editable')):return None
   b=n['bounds']
   if not isinstance(b,list) or len(b)!=4 or any(type(x) is not int for x in b):return None
   x1,y1,x2,y2=b
   if not 0<=x1<x2<=nw or not 0<=y1<y2<=nh:return None
   b=[x1*width//nw,y1*height//nh,(x2*width+nw-1)//nw,(y2*height+nh-1)//nh]
   clean.append(dict(n,bounds=b))
  return dict(package=obj['package'],width=width,height=height,nodes=clean,source='accessibility') if clean else None
 except (ValueError,TypeError,KeyError):return None

def bind(job,tree,raw,barrier,sequence):
 job.accessibility_frame=None if tree is None else dict(tree=tree,sha256=hashlib.sha256(raw).hexdigest(),barrier=barrier,sequence=sequence,session=job.screen_session)

def frame_hint(mailbox,job,raw):
 from . import app_screen
 # Same authority -> mailbox order as frame admission and revocation.
 with app_screen.AUTHORITY.lock,mailbox.lock:
  try:mailbox._live(job)
  except (ValueError,RuntimeError):return None
  if mailbox.jobs.get(job.device) is not job or job.done or job.cancelled:return None
  hint=getattr(job,'accessibility_frame',None);grant=app_screen.AUTHORITY.tickets.get(job.screen_session)
  if not hint or not grant or grant[0]<=app_screen.AUTHORITY.clock() or grant[1]!=job.device:return None
  if job.video_source!='user-consented-app-screen' or not 0<=mailbox.clock()-job.video_received<=2:return None
  if hint['session']!=job.screen_session or hint['barrier']!=job.video_barrier or hint['sequence']!=job.video_sequence:return None
  if raw!=job.video or hint['sha256']!=hashlib.sha256(raw).hexdigest():return None
  return copy.deepcopy(hint['tree'])

APPS={'支付宝':'com.eg.android.AlipayGphone','微信':'com.tencent.mm','美团':'com.sankuai.meituan','拼多多':'com.xunmeng.pinduoduo'}
LAUNCHERS={'com.miui.home','com.android.launcher','com.android.launcher3','com.google.android.apps.nexuslauncher','com.hihonor.android.launcher','com.huawei.android.launcher'}
def navigation_hint(tree,task):
 if not isinstance(tree,dict) or not isinstance(task,str):return None
 match=re.fullmatch(r'(?:请|帮我)?(?:打开|进入)(支付宝|微信|美团|拼多多)(?:的?账单(?:页面)?)?',task.strip())
 if not match:return None
 app=match[1];package=tree.get('package');label=None
 if package in LAUNCHERS:label=app
 # Alipay's two visible navigation tabs are read-only destinations. Financial
 # forms, completion, saving, and absent markers are never inferred here.
 elif package==APPS['支付宝'] and app=='支付宝' and '账单' in task:
  texts=[n.get('text') for n in tree.get('nodes',[])]
  if '账单' in texts:label='账单'
  elif '我的' in texts and not any(x in texts for x in ('账单详情','保存','该账单已添加')):label='我的'
 if label is None:return None
 hits=[n for n in tree.get('nodes',[]) if (n.get('text')==label or (not n.get('text') and n.get('description')==label)) and n.get('clickable') is True and n.get('editable') is False]
 if len(hits)!=1:return None
 w,h=tree.get('width'),tree.get('height');b=hits[0].get('bounds')
 if type(w) is not int or type(h) is not int or min(w,h)<=0 or not isinstance(b,list) or len(b)!=4:return None
 box=[n*1000//(w if i%2==0 else h) for i,n in enumerate(b)]
 if not 0<=box[0]<box[2]<=1000 or not 0<=box[1]<box[3]<=1000 or box[2]-box[0]>950 or box[3]-box[1]>400:return None
 return dict(safe=True,complete=False,screen='launcher' if package in LAUNCHERS else '支付宝',action='click',target_label=label,bounds=box,task=task,reader='accessibility_exact_target')
