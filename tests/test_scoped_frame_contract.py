"""Exercise the actual nested frame guard without importing a transport or a model."""
import ast
import os
from pathlib import Path
import unittest
from types import SimpleNamespace


class PermissionLost(Exception):
    pass


def frame_guard():
    path = Path(os.environ.get("SCOPED_FRAME_RUNTIME", "display_service/agent_runtime.py"))
    module = ast.parse(path.read_text(encoding="utf-8"))
    run = next(f for f in module.body if isinstance(f, ast.FunctionDef) and f.name == "run")
    execute = next(f for f in run.body if isinstance(f, ast.FunctionDef) and f.name == "execute")
    production_guard = next(c for c in execute.body if isinstance(c, ast.ClassDef) and c.name == "ScopedFrameGuard")
    job = object()
    control = {"permitted": True, "checks": 0, "revoke_during_match": False}

    def check_authority():
        control["checks"] += 1
        if not control["permitted"]:
            raise PermissionLost("synthetic revoked authority")

    def same_frame(expected, current):
        if control["revoke_during_match"]:
            control["permitted"] = False
        return expected == current

    command = {"op": "test-only", "position": (10, 15)}
    scope = dict(job=job, dispatch_live=check_authority, GateError=PermissionLost,
                 write_step={"marker": "ok"}, matches=same_frame, c=command,
                 _validate_write_frame=lambda step, hint: hint.get("marker") == step["marker"],
                 _save_locate=lambda step, hint: (hint.get("command"), None))
    tree = ast.Module(body=[production_guard], type_ignores=[])
    exec(compile(tree, str(path), "exec"), scope)
    guard = scope["ScopedFrameGuard"]()
    hint = {"marker": "ok", "command": command.copy()}
    guard.latest = SimpleNamespace(hint=lambda: hint)
    return guard, job, hint, control


class FrameCallProtocol(unittest.TestCase):
    def test_prior_call_keeps_both_authority_checks(self):
        guard, _, _, control = frame_guard()
        self.assertTrue(guard._matches_action_frame("frame-a", "frame-a", b"synthetic"))
        self.assertEqual(control["checks"], 2)

    def test_current_call_passes_same_job_positional_or_keyword(self):
        guard, job, _, _ = frame_guard()
        self.assertTrue(guard._matches_action_frame("frame-a", "frame-a", b"synthetic", job))
        self.assertTrue(guard._matches_action_frame("frame-a", "frame-a", b"synthetic", j=job))

    def test_foreign_job_never_reaches_match(self):
        guard, _, _, control = frame_guard()
        with self.assertRaises(PermissionLost):
            guard._matches_action_frame("a", "a", b"synthetic", object())
        self.assertEqual(control["checks"], 1)

    def test_final_frame_change_is_rejected(self):
        guard, job, _, _ = frame_guard()
        self.assertFalse(guard._matches_action_frame("planned-frame", "other-frame", b"synthetic", job))

    def test_changed_ocr_or_moved_coordinate_rejected(self):
        guard, job, hint, _ = frame_guard()
        hint["marker"] = "different"
        self.assertFalse(guard._matches_action_frame("a", "a", b"synthetic", job))
        hint.update(marker="ok", command={"op":"test-only", "position":(80, 88)})
        self.assertFalse(guard._matches_action_frame("a", "a", b"synthetic", job))

    def test_revocation_before_or_during_validation_is_rejected(self):
        guard, job, _, control = frame_guard()
        control["permitted"] = False
        with self.assertRaises(PermissionLost):
            guard._matches_action_frame("a", "a", b"synthetic", job)
        control.update(permitted=True, revoke_during_match=True)
        with self.assertRaises(PermissionLost):
            guard._matches_action_frame("a", "a", b"synthetic", job)


if __name__ == "__main__":
    unittest.main()
