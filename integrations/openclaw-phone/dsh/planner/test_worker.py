import json
import unittest
from worker import messages, parse_events, planning_provider


class PlanningContract(unittest.TestCase):
    def test_interactive_profile_preserves_subscription_and_other_models(self):
        selected = {"id": "deepseek-v4.1-flash", "compat": {"supportsDeveloperRole": False}}
        other = {"id": "another-model", "contextWindow": 4096}
        route = {"api": "openai-completions", "baseURL": "https://subscription.invalid",
                 "apiKeyEnv": "TEST_REF", "models": [selected, other.copy()]}
        selection = {"provider": "ocg", "model": selected["id"]}
        entries = [{"id": "llm-pi-ai", "config": {"providers": {"ocg": route}}},
                   {"id": "agent-default-model", "config": selection}]
        self.assertIs(planning_provider(entries), entries)
        self.assertEqual(selection["reasoningEffort"], "off")
        self.assertEqual(route["baseURL"], "https://subscription.invalid")
        self.assertEqual(route["apiKeyEnv"], "TEST_REF")
        self.assertEqual(route["models"][1], other)
        self.assertFalse(selected["compat"]["supportsDeveloperRole"])
        self.assertEqual(selected["compat"]["thinkingFormat"], "deepseek")
        self.assertEqual(route["retryPolicy"]["maxRetries"], 0)
        self.assertEqual(selected["reasoningEfforts"], {"off": None, "high": "high"})
        selection["provider"] = "another-route"
        with self.assertRaises(ValueError):
            planning_provider(entries)

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

    def test_only_a_completed_format_error_can_be_replanned(self):
        def final(text):
            return json.dumps({"type": "final", "reason": {"kind": "completed"}, "text": text})

        wrapped = final('```JSON\r\n{"goal": "test"}\r\n```')
        self.assertEqual(parse_events([wrapped])["proposal"], {"goal": "test"})
        for text in ('{"step": 1} {"step": 2}', 'answer: {"step": 1}', '[]', 'missing'):
            report = parse_events([final(text)])
            self.assertIsNone(report["proposal"])
            self.assertEqual(report["failureCode"], "INVALID_PLAN_JSON")
        report = parse_events(['{"type":"tool_call"}', final('missing')])
        self.assertIsNone(report["proposal"])
        self.assertNotIn("failureCode", report)
