"""Platform-aware generic tools and observation-bound SOP recipes.
Recipes confer no authority; only listed primitives execute through live fences.
"""
import copy
TOOL_SCHEMAS = {'home': {'effect': 'navigate',
          'fields': {'capability': 'home', 'target': '回桌面', 'locator': 'none', 'bounds': None},
          'meaning': '受支持HID回桌面；离开任意当前应用找目标可使用'},
 'open_app': {'effect': 'navigate',
              'fields': 'capability,target当前可见应用名,locator=text或icon,bounds当前图像边界或null',
              'meaning': '只点当前真实可见图标；找不到时探索文件夹/翻页，不编造目标'},
 'tap_text': {'effect': 'navigate',
              'fields': 'capability,target当前原样文字,locator=text,bounds可null',
              'meaning': '文字导航；优先当前OCR，漏识别时可请求图像定位'},
 'tap_icon': {'effect': 'navigate',
              'fields': 'capability,target图标语义,locator=icon,bounds当前visual_observation原图像素边界',
              'meaning': '纯导航图标'},
 'page': {'effect': 'navigate',
          'fields': 'capability,target容器语义,locator=region,bounds当前可滑动容器原图像素边界,direction=left/right/up/down,end=null',
          'meaning': '容器内标准翻页SOP，不猜全屏固定坐标'},
 'back': {'effect': 'navigate',
          'fields': 'capability,target=返回上一页,locator=none,bounds=null；也兼容当前可见返回控件locator=text或icon',
          'meaning': 'Android优先控制板原生Back，不提供坐标；每次有新画面再决定下一步；保留当前图标返回兼容'},
 'dismiss': {'effect': 'navigate',
             'fields': 'capability,target=下次再说/暂不开通/不同意/取消/关闭/稍后/返回/关闭弹窗,locator=text或icon,bounds',
             'meaning': '仅关闭/拒绝无关弹窗，不同意政策或授权'},
 'read_record': {'effect': 'observe',
                 'fields': 'capability=read_record,target,record={rows:{任意字段名:当前OCR明确row_index}}（仅read_only模式，执行器提取原文）；保存来源仍用record={values:{date,amount,merchant,order_id或occurred_at,currency可省略},rows:{字段:OCR索引}}',
                 'meaning': '冻结已显示的真实来源记录；不填表、不写入'},
 'save_record': {'effect': 'write',
                 'fields': 'capability,target=真实保存按钮文字,locator=text,bounds可null,record_identity来自progress,draft={values至少date/amount/merchant,rows},book={values:{book_name,account或unique_context},rows}',
                 'meaning': '仅原文明确授权保存，当前表单匹配冻结来源且账本唯一；先持久reserve后一次HID，结果不明不重试'}}
TOOL_SCHEMAS["reconcile_record"]={"effect":"observe","fields":"capability,target,record_identity来自progress,book={values:{book_name,account或unique_context},rows},saved={values:{status=已保存/已记账,order_id或date+amount+merchant},rows}","meaning":"只读核对真实已保存记录；可核查先前pending；不保存、不猜已保存、不重放"}
TOOL_SCHEMAS["type_text"]={"effect":"write","fields":"capability=type_text,target当前搜索框原样标签,locator=icon,bounds当前搜索框像素边界,text用户原文中的ASCII搜索词","meaning":"只在真实画面证实已聚焦、非密码搜索框时键入一次；不得改写搜索词，不自动提交；中文尚未接通"}
TOOL_SCHEMAS["adjust_brightness"]={"effect":"write","fields":"capability=adjust_brightness,target当前亮度滑条原样标签,locator=icon,bounds当前滑条轨道像素边界,value_percent原文明确的10至90整数百分比","meaning":"仅用户明确授权的屏幕亮度；通过当前真实像素填充边界向目标位置HID拖动，不改自动亮度等其他设置；需新画面核验"}
TOOL_SCHEMAS["edge_swipe"]={"effect":"navigate","fields":"capability=edge_swipe,target手势目的,locator=edge,bounds=null,edge=top/bottom/left/right,anchor_percent=5至95整数,distance_percent=20至80整数","meaning":"edge表示触点的起始边，滑动固定朝屏内：top向下、bottom向上、left向右、right向左。anchor_percent沿这条边定位：top/bottom为从左到右，left/right为从上到下。例：右上角向下拉控制中心=edge=top,anchor_percent=85,distance_percent=60；edge=right是向左的侧边手势，不能代替顶部下拉。起止点由当前几何生成，效果须新帧核验"}
PRESETS = {
 "open_visible_app":{"tools":["open_app"],"inputs":["app_name"],"verify":"实际目标应用内容，不以桌面图标当已打开"},
 "find_and_tap_text":{"tools":["tap_text"],"inputs":["target"],"verify":"动作后新画面；同帧OCR优先，歧义回规划器"},
 "go_back":{"tools":["back"],"inputs":["当前实际可见返回控件"],"verify":"新页面与预期前页一致"},
 "dismiss_dialog":{"tools":["dismiss"],"inputs":["实际可见关闭或拒绝控件"],"verify":"弹窗消失且没有同意或授权"},
 "page_container":{"tools":["page"],"inputs":["当前容器","direction"],"verify":"新帧内容变化；无变化时换策略"},
 "inspect_record":{"tools":["read_record"],"inputs":["当前OCR字段证据"],"verify":"记录身份和日期来自可追溯观察"},
 "save_unrecorded":{"tools":["read_record","save_record"],"inputs":["明确保存目标","目标账本","真实记录"],"verify":"持久占位、一次提交、关联新证据，未知不重做"}
}
def catalog(platform):
 platform=platform if platform in ("android","ios") else "unknown"
 tools=copy.deepcopy(TOOL_SCHEMAS);presets=copy.deepcopy(PRESETS)
 # Association evidence is being validated; keep experimental read reconciliation gated.
 import os
 if os.environ.get("EPAPER_AGENT_RECONCILE")!="1":tools.pop("reconcile_record",None)
 if platform=="android":
  presets["home_android"]={"tools":["home"],"inputs":[],"verify":"新帧为真实桌面"}
 else:
  tools.pop("edge_swipe",None)
  tools["back"]["fields"]="capability,target当前可见返回文字或箭头,locator=text或icon,bounds"
  tools["back"]["meaning"]="仅当前实际可见返回控件；该平台未验收硬件Back"
  tools.pop("home",None)
  if platform=="ios":
   presets["ios_home_menu"]={"tools":["tap_icon","tap_text"],"inputs":["当前识别到的AssistiveTouch菜单","当前主屏幕/Home项目"],"verify":"新帧为主屏幕","status":"not_tested"}
 return dict(platform=platform,tools=tools,presets=presets,
  device_verification="navigation_tested_record_writes_not_yet_verified" if platform=="android" else "not_tested",
  prerequisites=["当前整屏共享","当前HID许可","当前帧与回执围栏"]+(["用户已启用AssistiveTouch指针控制"] if platform=="ios" else []),
  reference="https://support.apple.com/guide/iphone/use-assistivetouch-iph96b21954/ios" if platform=="ios" else None)

import re
def is_commit_label(text):
 return isinstance(text,str) and bool(re.fullmatch(r"(?:立即|确认|一键|快速|新增|自动|手动)?(?:记账|记一笔|登记|录入|记录到账本|添加记录)(?:并继续|并返回|完成)?",text.strip()))
