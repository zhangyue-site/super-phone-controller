import json
import unittest
from summarize_events import summarize


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


if __name__ == "__main__":
    unittest.main()
