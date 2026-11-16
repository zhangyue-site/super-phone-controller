"""Typed, application-independent failures. Recovery never grants input authority."""
import re

class GateError(ValueError):
    def __init__(self, code, category, recovery, message, *, input_sent=False):
        super().__init__(message)
        self.code, self.category, self.recovery = code, category, recovery
        self.input_sent = input_sent

    def to_dict(self):
        return dict(code=self.code, category=self.category, recovery=self.recovery,
                    message=str(self), input_sent=self.input_sent, retry_input=False)


def failure(error, *, input_sent=False):
    # Once dispatch was entered, even an apparent validation error is unknown.
    if input_sent:
        return GateError("input_outcome_unknown", "outcome", "reconcile_original",
                         "输入可能已发出，请核查原动作和新画面，不重复执行。", input_sent=True)
    if isinstance(error, GateError):
        return error
    return GateError("execution_error", "internal", "stop", "执行检查失败，未获完整结果。")


# A policy link in a footer is not proof of a blocking modal. Explicit requests
# for permission/deletion remain blocked even when visual classification fails.
_MODAL_REQUEST = re.compile(r"是否允许|允许.{0,24}(?:访问|使用|获取)|(?:是否|确定|确认)(?:删除|卸载|清空)|同意并继续|同意后继续")


def dialog_present(hint, visual=None):
    return (any(permission_approval(str(r.get("text", ""))) for r in hint.get("lines", []))
            or any(_MODAL_REQUEST.search(str(r.get("text", ""))) for r in hint.get("lines", []))
            or bool(visual and any(r.get("role") == "dialog" for r in visual.get("regions", []))))

_PERMISSION_APPROVAL = re.compile(r"^(?:仅在使用中|仅此一次|始终允许|仅限这次|使用(?:App|APP|应用)(?:时|期间)允许|使用时允许|允许一次|仅允许一次|仅在使用该应用时允许|仅在使用此应用时允许|使用(?:App|APP|应用)时|仅在使用(?:该|此)?应用时|whileusing(?:the)?app|onlythistime|allowonce|allowalways)$", re.I)

def permission_approval(label):
    return isinstance(label,str) and bool(_PERMISSION_APPROVAL.fullmatch(re.sub(r"\s+","",label)))
