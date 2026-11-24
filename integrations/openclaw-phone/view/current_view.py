"""Recognize an explicit read of the currently shared screen."""
import re


_VIEW = r"(?:(?:手机(?:上)?的?)?(?:当前|现在|此时)的?(?:手机)?(?:画面|屏幕|页面|界面)|本页)"
_READ = r"(?:查看|读取|看看|描述|汇总|总结|列出|说明)"
_TOPIC = r"(?:(?:连接|网络|同步|运行|登录|共享|设备|任务|传输|当前)?状态|可见内容|可见文字|文字|内容|标题|提示|错误提示|按钮|选项)"
_HEAD = re.compile(r"(?:请)?(?:帮我)?(?:只读)?" + _READ + r"(?:一下)?" + _VIEW + r"(?:上的|上|的)?" + r"(?:" + _TOPIC + r")?")
_DETAIL = re.compile(_READ + r"(?:(?:当前|本)(?:界面|画面|屏幕|页面|页)(?:上)?(?:显示|可见)的)?" + _TOPIC)


def current_view_request(text, clarifications):
    if not isinstance(text, str) or clarifications:
        return False
    clauses = [s.strip() for s in re.split(r"[，,。；;！!]", text.strip()) if s.strip()]
    if not clauses or not _HEAD.fullmatch(clauses[0]):
        return False
    return all(s in {"只读", "不点击", "只读不点击", "读完停止"} or _DETAIL.fullmatch(s)
               for s in clauses[1:])


def current_view_label(value):
    return isinstance(value, str) and re.fullmatch(_VIEW, value) is not None
