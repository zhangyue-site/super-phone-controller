import unittest

from display_service.local_screen_results import LocalScreenResults


class LocalResultsTest(unittest.TestCase):
    def setUp(self):
        self.results = LocalScreenResults()
        self.grants = {"a": (200, "phone"), "b": (200, "other")}
        self.ocr = dict(run="a" * 32, epoch="1", frame="20", source="ocr",
                        count=10, state="done", ageMs=1000, text="真实界面")
        self.buttons = dict(run="b" * 32, epoch="1", frame="21", source="buttons",
                            count=1, state="running", ageMs=0, boxes=3)

    def record(self, rows, now=100, unlocked=True):
        self.results.record("a", "phone", self.grants, now, unlocked,
                            dict(v=1, platform="android", results=rows))

    def test_results_require_current_unlocked_device_grant(self):
        self.record([self.ocr, self.buttons])
        self.assertEqual([self.ocr, self.buttons], self.results.read("phone", self.grants, 101))
        self.assertEqual([], self.results.read("other", self.grants, 101))
        self.grants["new"] = (200, "phone")
        self.assertEqual([], self.results.read("phone", self.grants, 101))
        self.grants.pop("a")
        self.assertEqual([], self.results.read("phone", self.grants, 101))

    def test_repeated_heartbeat_does_not_refresh_same_frame(self):
        self.record([self.ocr])
        self.record([self.ocr], now=109)
        self.assertEqual([self.ocr], self.results.read("phone", self.grants, 110))
        self.assertEqual([], self.results.read("phone", self.grants, 112))

    def test_lock_and_missing_frames_clear_cached_text(self):
        self.record([self.ocr])
        self.record([self.ocr], now=101, unlocked=False)
        self.assertEqual([], self.results.read("phone", self.grants, 101))
        self.record([self.ocr])
        self.record([], now=101)
        self.assertEqual([], self.results.read("phone", self.grants, 101))

    def test_mixed_epochs_and_invalid_metadata_are_rejected(self):
        for row in (dict(self.buttons, epoch="2"), dict(self.buttons, count=11)):
            self.record([self.ocr])
            with self.assertRaises(ValueError):
                self.record([self.ocr, row], now=101)
            self.assertEqual([], self.results.read("phone", self.grants, 101))
