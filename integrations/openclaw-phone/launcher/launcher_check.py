"""Read-only recognition of the intermediate HOME effect for the Android Settings task."""

SETTINGS_TASK = "先按 HOME 回到系统桌面，等新画面，点击唯一的设置图标；验证系统设置首页后停止。"


def home_effect_is_visible(original, platform, pending, hint, observation, raw, *,
                           app_grid, body_hash, dialog_present):
    """Called after live authority/freshness checks. Never authorizes a click or completion."""
    if original != SETTINGS_TASK or platform != "android" or not pending:
        return False
    if pending.get("capability") != "home" or pending.get("receipt") != "confirmed":
        return False
    if observation is None or observation.blocked or hint.get("source") != "phone-ocr":
        return False
    before = pending.get("before_hint", {}).get("_observation") or {}
    after = hint.get("_observation") or {}
    for field in ("task_id", "device_id", "capture_session", "binding_id", "geometry"):
        if not before.get(field) or before[field] != after.get(field):
            return False
    try:
        before_seq = int(before["frame_id"].split(":", 1)[0])
        after_seq = int(after["frame_id"].split(":", 1)[0])
    except (ValueError, TypeError, KeyError, AttributeError):
        return False
    if after_seq <= before_seq or after.get("frame_id") != observation.frame_id:
        return False
    if dialog_present(hint) or observation.locate("设置") is None or not app_grid(hint):
        return False
    return bool(pending.get("before")) and body_hash(raw) != pending["before"]
