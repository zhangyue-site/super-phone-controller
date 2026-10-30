import ast,re,os,unittest
from pathlib import Path
source=Path(os.environ.get('GENERAL_NAV_SOURCE',str(Path(__file__).parent/'display_service/general_nav.py')))
tree=ast.parse(source.read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='GeneralNavigator');method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_validate_final');ns={'re':re};exec(compile(ast.Module(body=[method],type_ignores=[]),str(source),'exec'),ns);validate=ns['_validate_final']
class Tests(unittest.TestCase):
 def final(self,task,**kw):return dict(complete=True,verified=True,safe=True,task=task,application=kw.pop('application','设置'),evidence=kw.pop('evidence','系统设置实体键盘页面'),**kw)
 def test_exact_compound_settings_aliases_and_both_commas(self):
  for verb in ('打开','进入'):
   for app in ('设置','系统设置'):
    for comma in ('，',','):
     task=verb+app+comma+'进入系统的语言和输入法，在实体键盘页显示虚拟键盘'
     validate(None,self.final(task),task)
 def test_wrong_application_rejected_for_compound(self):
  task='打开设置，进入系统的语言和输入法'
  for app in ('浏览器','设置助手','系统设置页面',None):
   with self.assertRaises(ValueError):validate(None,self.final(task,application=app),task)
 def test_other_app_or_settings_substring_never_gets_alias_fallback(self):
  for task in ('打开设置助手，进入系统','打开浏览器，进入设置','打开设置evil,进入系统'):
   with self.assertRaises(ValueError):validate(None,self.final(task),task)
 def test_compound_search_does_not_bypass_app_or_query(self):
  for token in ('搜索','查找','找到'):
   task='打开设置，进入系统'+token+'蓝牙'
   for query in ('蓝牙','',None):
    with self.assertRaises(ValueError):validate(None,self.final(task,query=query,evidence='蓝牙'),task)
 def test_normal_search_keeps_exact_query_and_evidence(self):
  for task in ('打开设置搜索蓝牙','进入系统设置查找蓝牙','搜索蓝牙'):
   validate(None,self.final(task,query='蓝牙',evidence='蓝牙结果'),task)
   with self.assertRaises(ValueError):validate(None,self.final(task,query='蓝',evidence='蓝牙结果'),task)
   with self.assertRaises(ValueError):validate(None,self.final(task,query='蓝牙',evidence='空白页面'),task)
 def test_independent_verification_and_task_binding_unchanged(self):
  task='打开设置，进入系统'
  for field,value in (('verified',False),('safe',False),('complete',False),('task','另一个任务'),('evidence','')):
   value_dict=self.final(task);value_dict[field]=value
   with self.assertRaises(ValueError):validate(None,value_dict,task)
 def test_normal_single_app_exact_contract_is_preserved(self):
  for task,app in (('打开设置','设置'),('进入系统设置','设置'),('打开浏览器','浏览器')):validate(None,self.final(task,application=app),task)
  for task in ('打开浏览器','打开设置助手'):
   with self.assertRaises(ValueError):validate(None,self.final(task,application='设置'),task)
if __name__=='__main__':unittest.main()
