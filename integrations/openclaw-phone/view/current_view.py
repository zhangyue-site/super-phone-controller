"""Recognize an explicit read of the currently shared screen."""
import re
import unicodedata


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


def current_view_evidence(history, hint, verification=""):
    if not history or history[-1].get("state") != "observed_read_only" or hint.get("source") != "phone-ocr":
        return None
    values = history[-1].get("values")
    if not isinstance(values, dict) or not values:
        return None
    visible = [r.get("text") for r in hint.get("lines", []) if isinstance(r, dict)]
    cited = set(re.findall(r'[“「"]([^”」"\n]{1,300})[”」"]', verification))
    quotes = []
    for text in values.values():
        if not isinstance(text, str) or not text.strip():
            return None
        matches = [s for s in visible if isinstance(s, str) and s == text]
        if not matches:
            prior = unicodedata.normalize("NFKC", text).lstrip("*•● ").strip()
            for line in visible:
                if not isinstance(line, str) or not line.strip():
                    continue
                literal = unicodedata.normalize("NFKC", line).strip()
                # A visual badge may be merged into the previous OCR line. Reuse
                # only a complete, independently cited nonnumeric label on the final frame.
                trailing_badge = (line in cited and not any(c.isdigit() for c in literal)
                                  and re.fullmatch(re.escape(literal) + r"[)\]]\d{1,3}", prior))
                if literal == prior or trailing_badge:
                    matches.append(line)
        if len(matches) != 1:
            return None
        if matches[0] not in quotes:
            quotes.append(matches[0])
    return "本次画面显示" + "、".join("「" + text + "」" for text in quotes) + "。"
