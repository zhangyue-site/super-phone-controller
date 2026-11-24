import unittest
from current_view import current_view_evidence, current_view_label, current_view_request


class CurrentViewTest(unittest.TestCase):
    def test_answer_uses_verified_text_without_inferring_the_current_app(self):
        history = [{"state": "observed_read_only", "values": {"连接状态": "共享中"}}]
        hint = {"source": "phone-ocr", "lines": [{"text": "微信"}, {"text": "共享中"}]}
        self.assertEqual(current_view_evidence(history, hint), "本次画面显示「共享中」。")
        for lines in ([], [{"text": "已停止"}], [{"text": "共享中"}] * 2):
            self.assertIsNone(current_view_evidence(history, dict(hint, lines=lines)))
        self.assertIsNone(current_view_evidence(history, dict(hint, source="model")))
        self.assertIsNone(current_view_evidence([], hint))

    def test_badge_must_have_a_unique_current_quote_and_never_rewrites_amounts(self):
        h = [{"state": "observed_read_only", "values": {"state": "屏幕共享中)139"}}]
        frame = {"source": "phone-ocr", "lines": [{"text": "屏幕共享中"}]}
        self.assertIsNone(current_view_evidence(h, frame))
        self.assertIn("屏幕共享中", current_view_evidence(h, frame, "显示“屏幕共享中”"))
        self.assertIsNone(current_view_evidence(h, dict(frame, lines=frame["lines"] * 2), "“屏幕共享中”"))
        h[0]["values"]["state"] = "100)139"
        self.assertIsNone(current_view_evidence(h, dict(frame, lines=[{"text":"100"}]), "“100”"))

    def test_view_and_visible_question(self):
        for text in ("查看当前手机画面，汇总可见内容。只读，不点击。",
                     "只读查看手机当前画面，说明当前界面显示的连接状态，读完停止。",
                     "请帮我读取本页上的标题", "描述现在的手机屏幕"):
            self.assertTrue(current_view_request(text, []), text)
        for name in ("当前手机画面", "手机当前画面", "本页"):
            self.assertTrue(current_view_label(name))

    def test_named_source_and_other_tasks_keep_their_scope(self):
        for text in ("在支付宝查看当前手机画面", "查看当前手机画面，打开微信",
                     "查看当前手机画面，说明支付宝状态", "读取本页并保存",
                     "查看当前手机画面。读取支付宝账单。", "汇总当前页面后发给妈妈"):
            self.assertFalse(current_view_request(text, []), text)
        self.assertFalse(current_view_request("查看当前手机画面", ["限指定应用"]))
        self.assertFalse(current_view_label("阿柴记账"))
