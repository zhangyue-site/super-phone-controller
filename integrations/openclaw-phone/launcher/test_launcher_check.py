import unittest
from types import SimpleNamespace

from launcher_check import SETTINGS_TASK, home_effect_is_visible


class LauncherCheck(unittest.TestCase):
    def setUp(self):
        self.before = dict(task_id="task", device_id="device", capture_session="screen",
                           binding_id="lease", geometry={"width": 300, "height": 600}, frame_id="3:before")
        self.after = dict(self.before, frame_id="7:after")
        self.pending = dict(capability="home", receipt="confirmed", before="previous",
                            before_hint={"_observation": self.before})
        self.hint = dict(source="phone-ocr", _observation=self.after)
        self.observation = SimpleNamespace(blocked=False, frame_id="7:after", locate=lambda label: (4,8,12,16))
        self.gates = dict(app_grid=lambda hint: True, body_hash=lambda raw: "new", dialog_present=lambda hint: False)

    def check(self, original=SETTINGS_TASK, platform="android"):
        return home_effect_is_visible(original, platform, self.pending, self.hint, self.observation,
                                      b"fixture", **self.gates)

    def test_only_proves_intermediate_effect(self):
        self.assertIs(self.check(), True)

    def test_only_canonical_task_and_platform(self):
        self.assertFalse(self.check(SETTINGS_TASK + "再修改一项设置"))
        self.assertFalse(self.check(platform="ios"))

    def test_requires_receipt_of_home(self):
        for cap, receipt in (("back","confirmed"), ("home","pending"), ("home","unknown")):
            self.pending.update(capability=cap,receipt=receipt)
            self.assertFalse(self.check())

    def test_same_device_task_session_and_geometry(self):
        for field in ("task_id", "device_id", "capture_session", "binding_id", "geometry"):
            with self.subTest(field=field):
                self.hint["_observation"] = dict(self.after, **{field:"changed"})
                self.assertFalse(self.check())

    def test_observation_must_advance_and_match(self):
        for fid in ("3:before", "2:older", "invalid"):
            self.hint["_observation"] = dict(self.after, frame_id=fid)
            self.observation.frame_id = fid
            self.assertFalse(self.check())
        self.hint["_observation"] = self.after
        self.assertFalse(self.check())

    def test_requires_native_ocr_and_target(self):
        self.hint["source"] = "cloud"
        self.assertFalse(self.check())
        self.hint["source"] = "phone-ocr"
        self.observation.locate = lambda _: None
        self.assertFalse(self.check())

    def test_rejects_modal_blocked_page_and_unchanged_body(self):
        for name, result in (("dialog_present", True), ("body_hash", "previous"), ("app_grid",False)):
            with self.subTest(gate=name):
                original=self.gates[name]
                self.gates[name]=lambda _, value=result: value
                self.assertFalse(self.check())
                self.gates[name]=original
        self.observation.blocked=True
        self.assertFalse(self.check())

    def test_missing_evidence_falls_back(self):
        self.pending.pop("before")
        self.assertFalse(self.check())
        self.pending.pop("before_hint")
        self.assertFalse(self.check())


if __name__ == "__main__":
    unittest.main()
