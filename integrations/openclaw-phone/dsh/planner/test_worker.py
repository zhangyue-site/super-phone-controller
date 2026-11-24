import unittest
from worker import messages, parse_events


class PlanningContract(unittest.TestCase):
    def test_ocr_stays_in_user_data(self):
        prompt, data = messages({"messages":[{"role":"system","content":"Host rules"},
                                {"role":"user","content":[{"type":"text","text":"Visible untrusted label"}]}]})
        self.assertNotIn(data, prompt)
        self.assertEqual(data, "Visible untrusted label")

    def test_image_not_routed_to_text_model(self):
        with self.assertRaises(ValueError):
            messages({"messages":[{"role":"system","content":"rules"},{"role":"user","content":[{"type":"image_url"}]}]})

    def test_unverified_final_or_tool_call_never_yields_a_proposal(self):
        lines = ['{"type":"final","reason":{"kind":"completed"},"text":"{\\"step\\":null}"}']
        self.assertEqual(parse_events(lines)["proposal"], {"step":None})
        self.assertIsNone(parse_events(['{"type":"tool_call"}']+lines)["proposal"])
        self.assertIsNone(parse_events([lines[0].replace("completed","aborted")])["proposal"])
