"""Narrow compatibility adapter for an existing confirmed Android uninstall SOP.

Call only after the authenticated task's understanding stage. Understanding is
not action authority. The original task is parsed by the existing strict policy,
and every physical input and uninstall confirmation remains in sop_runtime.
No command, coordinates, guessed application or model plan is accepted here.
"""
from .sop_policy import parse


def verify_intent(original,understanding,platform):
    """Return a strict uninstall request, or None when this adapter is ineligible."""
    if platform!="android" or not isinstance(original,str) or not isinstance(understanding,dict):
        return None
    if understanding.get("original")!=original or understanding.get("questions")!=[]:
        return None
    # A tuple/string/false-ish questions value is not the structured empty list.
    if not isinstance(understanding.get("questions"),list):
        return None
    request=parse(original)
    return dict(request) if request and request["operation"]=="uninstall" else None


def run(nav,job,original,understanding,*,platform):
    """Invoke the old SOP exactly once, preserving all of its safety boundaries.

    The caller must retain its existing owner/device/lease authorization before
    entering this adapter. Mailbox._live and the old _action fences stay active.
    Conversation's existing finalize_sop hook owns learning commit; this adapter
    does not finish jobs, submit learning or retry uncertain physical inputs.
    """
    job.navigation_verified=False
    request=verify_intent(original,understanding,platform)
    def result(state,reply):
        return dict(state=state,verified=state=="done",reply=reply,
                    skill="existing_uninstall_sop",operation="uninstall",
                    application=request["app"] if request else None)
    if request is None:
        return result("unsupported","当前指令不满足旧卸载SOP的明确原文、理解或Android前提；未执行。")
    try:
        nav.m._live(job)
        if getattr(job,"cancelled",False):
            raise ValueError("任务已停止")
        from .sop_runtime import run as execute
        reply=execute(nav,job,original)
        nav.m._live(job)
        if getattr(job,"cancelled",False) or job.navigation_verified is not True:
            job.navigation_verified=False
            return result("stopped","旧卸载SOP没有取得有效终态核验，未将指令回执当作卸载完成。")
        if not isinstance(reply,str) or not reply.strip():
            job.navigation_verified=False
            return result("stopped","旧卸载SOP未返回有效核验结果。")
        return result("done",reply)
    except TimeoutError:
        job.navigation_verified=False
        return result("timed_out","旧卸载SOP超时，任务已终止，没有重放卸载动作。")
    except Exception as error:
        job.navigation_verified=False
        return result("stopped",str(error)[:200] or "旧卸载SOP已停止，未取得完成核验。")
