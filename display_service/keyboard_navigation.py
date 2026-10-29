"""Visually fenced USB input; no ADB or assumed candidate success."""
from copy import deepcopy
from .keyboard_input import pinyin_plan,choose_candidate,verify_candidate_commit,validate_target

def schema_issue_fields(o):
 """Only malformed type_text evidence may be reobserved, never negative evidence."""
 if not isinstance(o,dict) or o.get('action')!='type_text' or o.get('safe') is not True:return ()
 if o.get('input_visible') is False or o.get('input_focused') is False or o.get('input_password') is True:return ()
 if isinstance(o.get('input_role'),str) and o['input_role']!='search':return ()
 return tuple(k for k in ('input_visible','input_password','input_focused','input_role') if k not in o or (type(o[k]) is not str if k=='input_role' else type(o[k]) is not bool))

def _focused(o,frame):
 if o.get('safe') is not True or o.get('input_visible') is not True or o.get('input_focused') is not True or o.get('input_role')!='search' or o.get('input_password') is not False:raise ValueError('需要确认已聚焦的非密码搜索框')
 return validate_target(dict(purpose='visible_search',role='search',visible=True,focused=True,password=False,frame=frame))

def decision(plan,o,task,frame):
 """Return (command, next_state, observe_only); commit next_state after ACK."""
 if plan and plan.get('stage')=='select_candidate':
  _focused(o,frame)
  return None,verify_candidate_commit(plan,o.get('committed_text'),frame),True
 if plan and plan.get('stage') in ('type_pinyin','observe_candidates'):
  _focused(o,frame)
  if o.get('committed_text')==plan['desired_text']:
   result=deepcopy(plan);result.update(stage='complete',committed_prefix=plan['desired_text'],remaining='',frame=frame,verified=True)
   return None,result,True
  selection=choose_candidate(plan,o.get('candidates',[]),frame)
  x1,y1,x2,y2=selection['bounds']
  return dict(op='hid_pointer',kind='click',x=(x1+x2)*32767//2000,y=(y1+y2)*32767//2000),selection,False
 if o.get('action')=='type_text':
  text=o.get('text')
  if not isinstance(text,str) or not text or text not in task or o.get('safe') is not True:raise ValueError('输入文字必须来自当前搜索任务')
  if plan and plan.get('desired_text')==text:raise ValueError('搜索词已输入，不重复键入')
  state=pinyin_plan(text,_focused(o,frame))
  return dict(op='hid_text',text=state['ascii'],target=state['target']),state,False
 return None,plan,False
