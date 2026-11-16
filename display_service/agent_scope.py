"""Generic scope adapter: explicit task evidence bounds a model's proposal."""
import re
from datetime import date
def build(text,clarifications,info,*,today,journal_path):
 caps=set(info["capabilities"])
 if not caps & {"read_record","save_record"}:return None
 evidence="\n".join([text,*clarifications]);s=info["scope"]
 if "save_record" not in caps:
  # A read never borrows a destination or write grant from model suggestions.
  # Unnamed source is a namespace for the currently consented app, not a claim
  # that we have identified its package or may switch to a guessed application.
  source=s.get("source_app")
  if not isinstance(source,str) or not 1<=len(source)<=80 or source not in evidence:
   source="当前共享应用"
  def read_limit(value):
   if not isinstance(value,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",value):return None
   try:day=date.fromisoformat(value)
   except ValueError:return None
   explicit=any(v in evidence for v in (day.isoformat(),f"{day.year}年{day.month}月{day.day}日",f"{day.year}/{day.month}/{day.day}"))
   today_explicit=value==today and bool(re.search(r"今天|今日",evidence))
   return value if explicit or today_explicit else None
  start,end=read_limit(s.get("start")),read_limit(s.get("end"))
  if start is not None and end is not None and start>end:
   raise ValueError("记录日期范围倒置")
  return dict(source_app=source,target_app=None,start=start,end=end,mode="read_only",
              allow_save=False,journal_path=journal_path)
 for key in ("source_app","target_app"):
  name=s.get(key)
  if not isinstance(name,str) or not 1<=len(name)<=80 or name not in evidence:raise ValueError("记录来源或目标尚未由用户任务明确："+key)
 start=s.get("start");end=s.get("end")
 try:a=date.fromisoformat(start);b=date.fromisoformat(end)
 except (TypeError,ValueError):raise ValueError("记录任务缺少明确日期范围")
 if a>b:raise ValueError("记录日期范围倒置")
 def given(day):
  return any(v in evidence for v in (day.isoformat(),f"{day.year}年{day.month}月{day.day}日",f"{day.year}/{day.month}/{day.day}"))
 if not given(a) or end!=today and not given(b):raise ValueError("模型日期范围未得到任务或补充信息支持")
 allow_save=bool(re.search(r"保存|记账|录入|登记|save|record",text,re.I))
 if "save_record" in caps and not allow_save:raise ValueError("原文未授权记录写入")
 return dict(source_app=s["source_app"],target_app=s["target_app"],start=start,end=end,allow_save=allow_save,journal_path=journal_path)
