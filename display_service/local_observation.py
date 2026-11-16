"""Untrusted phone-side ROI stability facts. Never grants actuation authority."""
import copy,re
ROLES={'text_candidate','ad_skip_candidate','ad_close_candidate','agent_target'}
def validate(value,width,height):
 try:
  keys={'v','scopeHash','sourceSequence','sourceTimestampNs','sourceWidth','sourceHeight','ageMs','requiredFrames','minStableMs','regions','layoutHints'}
  if not isinstance(value,dict) or set(value)!=keys or type(value.get('v'))is not int or value['v']!=1:return None
  ranges={'sourceSequence':(1,2**63-1),'sourceTimestampNs':(1,2**63-1),'sourceWidth':(1,8192),'sourceHeight':(1,8192),'ageMs':(0,2500)}
  if any(type(value[k])is not int or not lo<=value[k]<=hi for k,(lo,hi) in ranges.items()):return None
  if type(value["requiredFrames"])is not int or value["requiredFrames"] not in (4,10) or value['minStableMs']!=600 or not isinstance(value['scopeHash'],str) or not re.fullmatch('[a-f0-9]{64}',value['scopeHash']):return None
  regions=value['regions'];hints=value['layoutHints']
  if not isinstance(regions,list) or len(regions)>64 or not isinstance(hints,list) or len(hints)>16:return None
  def bounds(b):return isinstance(b,list) and len(b)==4 and all(type(x)is int for x in b) and 0<=b[0]<b[2]<=width and 0<=b[1]<b[3]<=height
  def label(s):return isinstance(s,str) and 1<=len(s)<=160 and not any(ord(c)<32 for c in s)
  clean=[];ids=set()
  for r in regions:
   if not isinstance(r,dict) or set(r)!={'id','label','role','bounds','count','stableMs','ready'}:return None
   if not isinstance(r['id'],str) or not re.fullmatch('[A-Za-z0-9:_-]{1,96}',r['id']) or r['id']in ids:return None
   ids.add(r['id'])
   if not label(r['label']) or r['role']not in ROLES or not bounds(r['bounds']):return None
   if type(r['count'])is not int or not 0<=r['count']<=min(1000000,value['sourceSequence']) or type(r['stableMs'])is not int or not 0<=r['stableMs']<=86400000 or type(r['ready'])is not bool:return None
   row=copy.deepcopy(r);row['ready']=r['ready'] is True and r["count"]>=value["requiredFrames"] and r['stableMs']>=600;clean.append(row)
  for h in hints:
   if not isinstance(h,dict) or set(h)!={'kind','label','bounds'} or h['kind']not in {'ad_marker','ad_skip_candidate','ad_close_candidate','protected_surface'} or not label(h['label']) or not bounds(h['bounds']):return None
  return dict(copy.deepcopy(value),regions=clean,advisory=True)
 except (KeyError,TypeError,ValueError):return None

def ready_observation(hint,bounds,*,label=None,region_id=None):
 local=hint.get('local_observation')
 if not isinstance(local,dict) or local.get('ageMs',99999)>2500:return None
 for r in local.get('regions',[]):
  if region_id is not None and r['id']!=region_id:continue
  if region_id is None and label!=r['label']:continue
  if max(abs(a-b) for a,b in zip(r['bounds'],bounds))>3:continue
  if r.get('ready')is True and r["count"]>=local.get("requiredFrames",10) and r['stableMs']>=600:return dict(r,sourceSequence=local.get('sourceSequence'),sourceTimestampNs=local.get('sourceTimestampNs'),scopeHash=local.get('scopeHash'),ageMs=local.get('ageMs'))
 return None

def ready_region(hint,bounds,*,label=None,region_id=None):
 return ready_observation(hint,bounds,label=label,region_id=region_id)is not None
