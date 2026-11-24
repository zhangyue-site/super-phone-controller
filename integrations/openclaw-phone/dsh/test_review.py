import json
import contextlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from summarize_events import summarize
import task_status_mcp


class ReceiptTest(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.data = {"status": {"terminal": True, "verified": False}, "progress": {"actionIntents": 0}}
        for key, value in self.data.items():
            self.events.extend([dict(type="tool_call", callId=key, tool="mcp__phone__task_"+key, input={}),
                                dict(type="tool_result", callId=key, status="completed", result=json.dumps(value))])
        self.events += [dict(type="final", text=json.dumps(self.data))]

    def review(self):
        return summarize(map(json.dumps,self.events))

    def test_verified_pair(self):
        self.assertEqual(self.review()["tools"], self.data)

    def test_mismatch_and_invented_success_rejected(self):
        self.events[-1]["text"] = '{"status":{"verified":true}}'
        with self.assertRaises(ValueError): self.review()

    def test_status_alone_insufficient(self):
        self.events = self.events[:2] + self.events[-1:]
        with self.assertRaises(ValueError): self.review()

    def test_unbound_parameters_rejected(self):
        self.events[0]["input"] = {"task_id":"foreign"}
        with self.assertRaises(ValueError): self.review()


class DirectReceiptTest(unittest.TestCase):
    def test_bound_identity_is_checked_before_each_read(self):
        task = "a" * 32
        with TemporaryDirectory() as directory:
            bridge = Path(directory) / "bridge.py"
            header = ("from pathlib import Path\nSTATE = Path(__file__).parent\n"
                      "def _authorized_status(ident):\n"
                      "    return {'task_id': next(ids), 'state': 'expired', 'terminal': True, 'verified': False}\n")
            with patch.object(task_status_mcp, "BRIDGE", bridge):
                bridge.write_text(header + f"ids = iter([{task!r}, {task!r}])\n")
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    task_status_mcp.main(task, receipts_only=True)
                data = json.loads(output.getvalue())
                self.assertEqual(data["task"], task)
                self.assertEqual(data["progress"], {"resultAvailable": False})
                self.assertEqual(data["modelCalls"], 0)
                bridge.write_text(header + f"ids = iter([{task!r}, 'other-device-task'])\n")
                with self.assertRaisesRegex(ValueError, "binding changed"):
                    task_status_mcp.main(task, receipts_only=True)


if __name__ == "__main__":
    unittest.main()
