import unittest
from display_service.general_nav import GeneralNavigator
class SearchGoal(unittest.TestCase):
 def test_standalone_search_requires_exact_query(self):
  n=GeneralNavigator(object(),object());v=dict(complete=True,verified=True,safe=True,task='搜索北京',evidence='可见背景结果',query='背景',application='搜索')
  with self.assertRaises(ValueError):n._validate_final(v,'搜索北京')
  v.update(query='北京',evidence='可见北京搜索结果');n._validate_final(v,'搜索北京')
 def test_settings_alias_does_not_reject_real_settings(self):
  n=GeneralNavigator(object(),object());v=dict(complete=True,verified=True,safe=True,task='打开系统设置',evidence='设置标题和网络电池列表',query='',application='设置')
  n._validate_final(v,'打开系统设置')
if __name__=='__main__':unittest.main()
