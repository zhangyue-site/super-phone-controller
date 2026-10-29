"""USB keyboard search planning. Reports require subsequent visual verification.

Chinese conversion needs pypinyin==0.55.0; no network or fallback is attempted.
"""
import re
from contextvars import ContextVar
from contextlib import contextmanager
from copy import deepcopy

KEY_OP=13
TEXT_OP=14
KEY_USAGES=frozenset((*range(0x04,0x28),*range(0x28,0x2d),*range(0x4f,0x53)))

def ascii_chunks(text):
 if not isinstance(text,str) or not 1<=len(text)<=256 or any(not 0x20<=ord(c)<=0x7e for c in text):raise ValueError('printable ASCII text required')
 return [pack_ascii(text[i:i+8]) for i in range(0,len(text),8)]

def pack_ascii(text):
 if not isinstance(text,str) or not 1<=len(text)<=8 or any(not 0x20<=ord(c)<=0x7e for c in text):raise ValueError('ASCII fragment')
 b=text.encode('ascii').ljust(8,b'\0')
 return [len(text)]+[b[i]|(b[i+1]<<8) for i in range(0,8,2)]

def validate_target(target):
 if not isinstance(target,dict) or target.get('purpose')!='visible_search' or target.get('visible') is not True or target.get('focused') is not True or target.get('password') is not False or not isinstance(target.get('frame'),int) or isinstance(target.get('frame'),bool) or target['frame']<1:raise ValueError('visible focused search target required')
 if target.get('role')!='search':raise ValueError('search role required')
 return dict(target)

def validate_command(command):
 validate_target(command.get('target'))
 if command.get('op')=='hid_text':return [(TEXT_OP,a) for a in ascii_chunks(command.get('text'))]
 if command.get('op')=='hid_key':
  modifier=command.get('modifier',0);usage=command.get('usage')
  # Search planning needs backspace, escape and arrows. Enter and Tab can submit
  # or leave the visually fenced field, so are deliberately unavailable here.
  if type(modifier) is not int or modifier!=0 or type(usage) is not int or usage not in (0x29,0x2a,0x4f,0x50,0x51,0x52):raise ValueError('search key rejected')
  return [(KEY_OP,[modifier,usage,0,0,0])]
 raise ValueError('keyboard command')

def _romanize(text):
 if text.isascii():return text
 try:from pypinyin import lazy_pinyin,Style
 except ImportError as exc:raise RuntimeError('install pinned pypinyin==0.55.0 before Chinese search') from exc
 def unmapped(chars):
  # ASCII runs are deliberately preserved; an unknown Han character fails.
  if chars.isascii():return chars
  raise ValueError('unmapped search character')
 syllables=lazy_pinyin(text,style=Style.NORMAL,errors=unmapped)
 if any(not re.fullmatch(r'[a-zA-Z0-9 ]+',v) for v in syllables):raise ValueError('unsupported pinyin spelling')
 return ''.join(syllables)

def pinyin_plan(text,target):
 validate_target(target)
 if not isinstance(text,str) or not 1<=len(text)<=64 or not re.fullmatch(r'[\u3400-\u9fffA-Za-z0-9 ]+',text):raise ValueError('search text')
 typed=_romanize(text);ascii_chunks(typed)
 return {'text':text,'desired_text':text,'ascii':typed,'typed_pinyin':typed,'stage':'type_pinyin','committed_prefix':'','remaining':text,'target':dict(target),'frame':target['frame'],'next':'observe_candidates','verified':False}

def _state(plan):
 if not isinstance(plan,dict):raise ValueError('input plan')
 desired=plan.get('desired_text',plan.get('text'));prefix=plan.get('committed_prefix','');remaining=plan.get('remaining',desired)
 if not isinstance(desired,str) or not desired or not isinstance(prefix,str) or not isinstance(remaining,str) or prefix+remaining!=desired:raise ValueError('inconsistent input state')
 validate_target(plan.get('target'))
 return desired,prefix,remaining

def candidate_plan(plan,observed_text,frame,bounds):
 desired,prefix,pending=_state(plan)
 barrier=max(plan['target']['frame'],plan.get('frame',0))
 if plan.get('stage') not in ('type_pinyin','observe_candidates') or not pending or not isinstance(observed_text,str) or not observed_text or not pending.startswith(observed_text) or type(frame) is not int or frame<=barrier:raise ValueError('fresh target-prefix candidate required')
 if not isinstance(bounds,(list,tuple)) or len(bounds)!=4 or any(type(v) is not int or not 0<=v<=1000 for v in bounds) or not(bounds[0]<bounds[2] and bounds[1]<bounds[3]):raise ValueError('candidate bounds')
 result=deepcopy(plan)
 result.update(stage='select_candidate',text=observed_text,desired_text=desired,selected_prefix=observed_text,remaining=pending[len(observed_text):],committed_prefix=prefix,expected_prefix=prefix+observed_text,frame=frame,bounds=list(bounds),next='verify_search_text',verified=False,exact_candidate=observed_text==pending)
 return result

def choose_candidate(plan,candidates,frame):
 """Validate observed candidates, preferring the whole pending phrase."""
 _state(plan)
 if not isinstance(candidates,list):raise ValueError('candidate observations')
 accepted=[]
 for item in candidates:
  if not isinstance(item,dict):raise ValueError('candidate observation')
  try:accepted.append(candidate_plan(plan,item.get('text'),frame,item.get('bounds')))
  except ValueError:continue
 if not accepted:raise ValueError('no target candidate observed')
 return max(accepted,key=lambda p:len(p['selected_prefix']))

def verify_candidate_commit(selection,observed_input,frame):
 # The caller must use the actual focused input text from a later image.
 if not isinstance(selection,dict) or selection.get('stage')!='select_candidate' or observed_input!=selection.get('expected_prefix') or type(frame) is not int or frame<=selection['frame']:raise ValueError('fresh exact input-prefix verification required')
 result=deepcopy(selection);prefix=selection['expected_prefix'];remaining=selection['remaining']
 if prefix+remaining!=selection['desired_text']:raise ValueError('inconsistent candidate selection')
 result.update(text=selection['desired_text'],committed_prefix=prefix,frame=frame,stage='observe_candidates' if remaining else 'complete',next='observe_candidates' if remaining else 'verify_search_results',verified=not bool(remaining))
 return result

_OBSERVATION_CONTEXT=ContextVar('keyboard_observation_context',default=None)

@contextmanager
def observation_context(plan):
 """Task-local prompt data only. Never dispatches or assumes an action."""
 if plan.get('stage')!='select_candidate':_state(plan)
 else:
  if plan.get('expected_prefix','')+plan.get('remaining','')!=plan.get('desired_text'):raise ValueError('inconsistent candidate selection')
 token=_OBSERVATION_CONTEXT.set(deepcopy(plan))
 try:yield current_observation_context()
 finally:_OBSERVATION_CONTEXT.reset(token)

def current_observation_context():
 return deepcopy(_OBSERVATION_CONTEXT.get())
