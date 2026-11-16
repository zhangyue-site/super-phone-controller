"""Task authority and same-frame locators, independent of device or app name."""
import re
from .dialogue import DENY
SOPS={"tap_text","tap_icon","hold_app","page","uninstall_entry","confirm_uninstall"}
def parse(task):
 if not isinstance(task,str):return None
 task=task.strip().rstrip("。！？!?")
 m=re.fullmatch(r"(?:请|帮我)?(打开|进入|卸载)([\w\u4e00-\u9fff .+\-]{1,32})",task)
 if not m:return None
 app=m[2].strip()
 if not app or re.search(r"并|然后|之后|发送|删除|转账|付款|登录|授权|权限|全部|所有|系统应用|账单|搜索|找到|查找|查看|http",app,re.I) or app in ("支付","安装","卸载","保存","提交"):return None
 return dict(operation="uninstall" if m[1]=="卸载" else "open",app=app,task=task)
def box(b,w,h):
 if not isinstance(b,list) or len(b)!=4 or any(type(v)is not int for v in b) or not 0<=b[0]<b[2]<=w or not 0<=b[1]<b[3]<=h:raise ValueError("SOP目标坐标无效")
 return b

def ocr_target(hint,target,coarse=None):
 if not hint or not isinstance(target,str):return None
 key=lambda s:re.sub(r"\s+","",s)
 hits=[]
 for row in hint["lines"]:
  if key(row["text"])!=key(target):continue
  b=row["bounds"]
  if coarse is not None and not (coarse[0]<=(b[0]+b[2])/2<=coarse[2] and coarse[1]<=(b[1]+b[3])/2<=coarse[3]):continue
  hits.append(b)
 return list(hits[0]) if len(hits)==1 else None

SENSITIVE=re.compile(r"同意|允许|接受|确定|确认|继续|下一步|开始|马上|立即|启用|开通|连接|完成|更新|取消|清理|清除|停用|强行停止|恢复|重置")
DIALOG_MARKERS=re.compile(r"隐私政策|隐私保护|服务协议|用户协议|是否允许|允许.*访问|仅在使用中|同意并继续|同意后继续|登录后|登录或注册|^确定$|^取消$|确认删除|是否删除|确定删除|是否卸载|卸载[“\"]")
def uninstall_identity(hint,app):
 if not hint:return False
 texts=[re.sub(r"\s+","",r["text"]) for r in hint["lines"]]
 target=re.sub(r"\s+","",app);identities=[]
 for text in texts:
  # A standalone app label may be background and cannot bind this dialog.
  m=re.fullmatch(r"(?:是否|确定要|确认|要|确定)?卸载(?:应用)?[“\"「『]([^”\"」』]+)[”\"」』](?:吗)?[？?。！!]?",text)
  if m:identities.append(m[1]);continue
  m=re.fullmatch(r"(?:是否|确定要|确认|要|确定)?卸载(?:应用)?(.+?)(?:吗)?[？?]",text)
  if m:identities.append(m[1])
 return bool(identities) and all(v==target for v in identities) and "取消" in texts and any("卸载" in t for t in texts)

def validate_step(step,req,hint,phase):
 if not isinstance(step,dict) or set(step)-{"sop","target","locator","bounds","end","direction","screen","evidence","expected","dialog_bounds"}:raise ValueError("SOP字段无效")
 s=step.get("sop");target=step.get("target","");loc=step.get("locator")
 if step.get("screen") in ("unknown","dialog") and not (s=="confirm_uninstall" and phase=="confirm"):raise ValueError("未知页或非授权弹窗不能操作")
 if s not in SOPS or loc not in ("text","icon","region") or not isinstance(target,str) or not 1<=len(target)<=80:raise ValueError("SOP规划无效")
 allowed_locators={"tap_text":("text",),"tap_icon":("icon",),"hold_app":("text","icon"),"page":("region",),"uninstall_entry":("text","icon"),"confirm_uninstall":("text",)}
 if loc not in allowed_locators[s]:raise ValueError("定位器不能替代SOP语义")
 if hint is None and loc=="text":raise ValueError("尚未收到手机OCR，不能猜测文字坐标")
 w,h=(hint["width"],hint["height"]) if hint else (0,0)
 if step.get("bounds") is not None:box(step["bounds"],w,h)
 if loc in ("icon","region") and step.get("bounds") is None:raise ValueError("图像目标缺少当前帧定位")
 if phase=="menu" and s!="uninstall_entry" and not (s in ("tap_text","tap_icon") and target in ("应用信息","应用详情","应用信息图标")):raise ValueError("卸载菜单只允许卸载或应用信息入口")
 if phase=="app_info" and s not in ("uninstall_entry","page"):raise ValueError("应用信息仅允许查找并进入卸载")
 if req["operation"]=="uninstall" and phase=="locate" and target==req["app"] and s!="hold_app":raise ValueError("卸载任务只可长按指定应用，不启动业务页面")
 if s=="hold_app" and (req["operation"]!="uninstall" or target!=req["app"] or phase!="locate"):raise ValueError("长按不属于当前应用任务")
 if s=="uninstall_entry" and (req["operation"]!="uninstall" or phase not in ("menu","app_info") or target not in ("卸载","卸载图标")):raise ValueError("未授权当前卸载入口")
 if s=="confirm_uninstall":
  db=box(step.get("dialog_bounds"),w,h)
  dialog=dict(hint,lines=[r for r in hint["lines"] if db[0]<=(r["bounds"][0]+r["bounds"][2])/2<=db[2] and db[1]<=(r["bounds"][1]+r["bounds"][3])/2<=db[3]])
  if not uninstall_identity(dialog,req["app"]):raise ValueError("当前确认框没有明确绑定指定应用")
  button=ocr_target(dialog,target,step.get("bounds"))
  if button is None or not (db[0]<=button[0]<button[2]<=db[2] and db[1]<=button[1]<button[3]<=db[3]):raise ValueError("确认按钮未在当前确认框内唯一定位")
  step=dict(step,bounds=button)
  if step.get("bounds") and not (db[0]<=step["bounds"][0]<step["bounds"][2]<=db[2] and db[1]<=step["bounds"][1]<step["bounds"][3]<=db[3]):raise ValueError("确认按钮未位于当前确认框")
 if s=="confirm_uninstall" and (req["operation"]!="uninstall" or phase!="confirm" or target not in ("卸载","确定") or loc!="text"):raise ValueError("卸载确认未匹配指定应用")
 if s not in ("confirm_uninstall","uninstall_entry") and any(DIALOG_MARKERS.search(r["text"]) for r in hint["lines"]):raise ValueError("检测到协议或权限页面，未授权继续")
 if SENSITIVE.search(target) and target!=req["app"] and s!="confirm_uninstall":raise ValueError("确认类目标不属于应用导航")
 if loc=="icon" and s not in ("confirm_uninstall","uninstall_entry"):
  b=step["bounds"]
  if any(SENSITIVE.search(r["text"]) and b[0]<=(r["bounds"][0]+r["bounds"][2])/2<=b[2] and b[1]<=(r["bounds"][1]+r["bounds"][3])/2<=b[3] for r in hint["lines"]):raise ValueError("图标区域覆盖确认类控件")
 scoped=target==req["app"] or s in ("uninstall_entry","confirm_uninstall")
 if DENY.search(target) and not scoped:raise ValueError("SOP目标超出导航授权")
 if s in ("tap_text","tap_icon") and phase in ("confirm","after"):raise ValueError("当前阶段不接受自由点击")
 if s=="page":
  end=step.get("end")
  if not isinstance(end,list) or len(end)!=2 or any(type(v)is not int for v in end) or not 0<=end[0]<=w or not 0<=end[1]<=h:raise ValueError("翻页终点缺少当前图像依据")
  if loc!="region":raise ValueError("翻页必须定位当前可见区域")
 return dict(step)
