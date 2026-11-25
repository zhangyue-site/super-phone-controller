import unittest
from types import SimpleNamespace

from launcher_check import has_application_steps, home_effect_is_visible, unique_launcher_target


class LauncherCheck(unittest.TestCase):
    def setUp(self):
        self.before = dict(task_id="task", device_id="device", capture_session="screen",
                           binding_id="lease", geometry={"width": 300, "height": 600}, frame_id="3:before")
        self.after = dict(self.before, frame_id="7:after")
        self.pending = dict(capability="home", receipt="confirmed", before="previous",
                            before_hint={"_observation": self.before})
        self.hint = dict(source="phone-ocr", _observation=self.after, lines=[{"text": n} for n in ("Atlas", "日历", "天气")])
        self.observation = SimpleNamespace(blocked=False, frame_id="7:after", locate=lambda label: (4,8,12,16))
        self.gates = dict(app_grid=lambda hint: True, body_hash=lambda raw: "new", dialog_present=lambda hint: False)

    def check(self):
        return home_effect_is_visible(self.pending, self.hint, self.observation,
                                      b"fixture", **self.gates)

    def test_only_proves_intermediate_effect(self):
        self.assertIs(self.check(), True)

    def test_names_and_task_wording_do_not_select_implementation(self):
        for name in ("天气", "设置", "Atlas Notes", "没有预注册过的应用"):
            self.assertTrue(has_application_steps({"target_app": name}, ["home","open_app"]))
        self.assertFalse(has_application_steps({"target_app": "桌面"}, ["home","observe","verify"]))
        self.assertFalse(has_application_steps({}, ["home","open_app"]))

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

    def test_requires_native_ocr_but_no_particular_app(self):
        self.hint["source"] = "cloud"
        self.assertFalse(self.check())
        self.hint["source"] = "phone-ocr"
        self.observation.locate = lambda _: None
        self.assertTrue(self.check())

    def test_rejects_modal_blocked_page_and_unchanged_body(self):
        for name, result in (("dialog_present", True), ("body_hash", "previous"), ("app_grid",False)):
            with self.subTest(gate=name):
                original=self.gates[name]
                self.gates[name]=lambda _, value=result: value
                self.assertFalse(self.check())
                self.gates[name]=original
        self.observation.blocked=True
        self.assertFalse(self.check())

    def test_exact_target_is_data_from_the_request(self):
        layout = {"时钟": (2, 10, 15, 16), "Atlas Notes": (42, 10, 60, 16)}
        self.observation.locate = layout.get
        def locate(name):
            return unique_launcher_target(name, self.hint, self.observation,
                app_grid=self.gates["app_grid"], dialog_present=self.gates["dialog_present"])
        for name, box in layout.items():
            self.assertEqual(locate(name), box)
        self.assertIsNone(locate("Atlas"))
        self.assertIsNone(locate("不存在"))
        self.observation.blocked = True
        self.assertIsNone(locate("时钟"))

    def test_pin_keypad_and_lock_screen_do_not_count_as_launcher(self):
        self.hint["lines"] = [{"text": str(n)} for n in range(10)]
        self.assertFalse(self.check())
        self.hint["lines"] += [{"text": n} for n in ("ABC", "DEF", "Emergency call")]
        self.assertFalse(self.check())

    def test_missing_evidence_falls_back(self):
        self.pending.pop("before")
        self.assertFalse(self.check())
        self.pending.pop("before_hint")
        self.assertFalse(self.check())


if __name__ == "__main__":
    unittest.main()
