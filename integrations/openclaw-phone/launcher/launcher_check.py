"""Local, read-only observation of launcher transitions on a consented phone."""


def _launcher_surface(hint, app_grid, dialog_present):
    if dialog_present(hint) or not app_grid(hint):
        return False
    labels = {row["text"].strip() for row in hint["lines"]}
    if any(marker in label.casefold() for label in labels for marker in
           ("紧急呼叫", "锁屏密码", "emergency call", "enter passcode")):
        return False
    return len({label for label in labels if any(char.isalpha() for char in label)}) >= 3


def home_effect_is_visible(pending, hint, observation, raw, *,
                           app_grid, body_hash, dialog_present):
    """Recognize the common HOME effect using the caller's trusted frame and receipt.

    Capability and platform support are checked by the caller when dispatching HOME.
    This predicate has no application name, user prompt, action output or task outcome.
    """
    if not pending or pending.get("capability") != "home" or pending.get("receipt") != "confirmed":
        return False
    if observation is None or observation.blocked or hint.get("source") != "phone-ocr":
        return False
    before = (pending.get("before_hint") or {}).get("_observation") or {}
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
    if not _launcher_surface(hint, app_grid, dialog_present):
        return False
    return bool(pending.get("before")) and body_hash(raw) != pending["before"]


def has_application_steps(scope, capabilities):
    """Keep the normal goal verification for HOME-only and observation-only tasks."""
    return bool(isinstance(scope.get("target_app"), str) and scope["target_app"].strip()
                and {"open_app", "tap_icon", "tap_text", "read_record", "save_record"}.intersection(capabilities))


def unique_launcher_target(label, hint, observation, *, app_grid, dialog_present):
    """Return the current OCR box for an explicitly supplied label on a launcher."""
    if not isinstance(label, str) or not label.strip() or observation is None or observation.blocked:
        return None
    if hint.get("source") != "phone-ocr" or hint.get("_observation", {}).get("frame_id") != observation.frame_id:
        return None
    if not _launcher_surface(hint, app_grid, dialog_present):
        return None
    return observation.locate(label)
