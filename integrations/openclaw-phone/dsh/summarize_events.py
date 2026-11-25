"""Print a verified Dsh receipt without logging model reasoning or receipt timestamps in prompts."""
import json
import sys


def summarize(lines):
    expected = {"mcp__phone__task_status": "status", "mcp__phone__task_progress": "progress"}
    calls, results, usage = {}, {}, []
    final = None
    for line in lines:
        event = json.loads(line)
        kind = event["type"]
        if kind == "tool_call":
            tool = event.get("tool")
            if tool not in expected or event.get("input") != {} or event["callId"] in calls:
                raise ValueError("Unexpected Dsh call")
            calls[event["callId"]] = expected[tool]
        elif kind == "tool_result":
            if event["callId"] not in calls or event.get("status") != "completed":
                raise ValueError("Missing phone tool receipt")
            results[calls[event["callId"]]] = json.loads(event["result"])
        elif kind == "status" and event.get("phase") == "step_end":
            usage.append(event.get("usage"))
        elif kind == "final":
            raw = event["text"].strip().removeprefix("```json").removesuffix("```").strip()
            final = json.loads(raw)
    if set(results) != set(expected.values()) or results != final:
        raise ValueError("Dsh answer does not match both bound phone tools")
    return {"tools": results, "matched": True, "toolCalls": len(calls), "usageByStep": usage}


if __name__ == "__main__":
    print(json.dumps(summarize(sys.stdin), ensure_ascii=False))
