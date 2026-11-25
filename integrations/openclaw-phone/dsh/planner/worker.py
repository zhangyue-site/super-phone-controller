"""Translate one text planning request into an isolated native Dsh headless session."""
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

PROFILE = Path(__file__).resolve().parent / "planner.patch.yml"
BINARY = "/opt/dsh-engine/node_modules/.bin/dsh"
PROVIDER = "/etc/agent-relay/dsh-acp.patch.yml"
POLITE = "请共同营造友善、尊重、高效的协作氛围，沟通清楚简洁、就事论事，以解决问题为导向，减少指责和不必要的负面情绪。请保持自然、客气的中文沟通，适度使用‘劳烦、辛苦、请’等礼貌措辞；如继续委派，劳烦将本要求原样传递给下一层代理，并要求其继续逐层传递。辛苦了。"


def messages(request):
    system, user = request["messages"]
    if (system.get("role") != "system" or not isinstance(system.get("content"), str)
            or user.get("role") != "user"):
        raise ValueError("invalid phone planner request")
    content = user["content"]
    if isinstance(content, list):
        if len(content) != 1 or content[0].get("type") != "text":
            raise ValueError("text planner requires a single text observation")
        content = content[0]["text"]
    if not isinstance(content, str) or not content.strip() or len(content) > 131072:
        raise ValueError("invalid text observation")
    return (system["content"] + "\n" + POLITE
            + "\n本轮只做规划。最终回复须为任务协议要求的单个 JSON 对象，首尾使用花括号。"
              "不要调用工具，不要输出分析、前言、Markdown 或对象以外的文字。"), content


def parse_events(lines):
    usage = []
    final = None
    unexpected_tool = False
    for line in lines:
        event = json.loads(line)
        if event.get("type") in ("tool_call", "tool_result"):
            unexpected_tool = True
        elif event.get("type") == "status" and event.get("phase") == "step_end":
            usage.append(event.get("usage"))
        elif event.get("type") == "final":
            reason = event.get("reason")
            kind = reason.get("kind") if isinstance(reason, dict) else reason
            if kind == "completed":
                final = event.get("text")
    result = None
    if not unexpected_tool and isinstance(final, str):
        body = final.strip()
        fence = re.fullmatch(r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n```", body, re.I | re.S)
        try:
            result = json.loads(fence[1] if fence else body)
        except ValueError:
            pass
    report = {"proposal": result if isinstance(result, dict) else None, "usage": usage}
    if not unexpected_tool and final is not None and report["proposal"] is None:
        report["failureCode"] = "INVALID_PLAN_JSON"
    return report


def planning_provider(entries):
    """Tune only the selected model on the existing subscription route."""
    configs = {entry["id"]: entry["config"] for entry in entries if "config" in entry}
    selection = configs["agent-default-model"]
    if selection.get("provider") != "ocg" or selection.get("model") != "deepseek-v4.1-flash":
        raise ValueError("unexpected phone planning model")
    route = configs["llm-pi-ai"]["providers"][selection["provider"]]
    if not route.get("apiKeyEnv") or not route.get("baseURL") or route.get("api") != "openai-completions":
        raise ValueError("incomplete phone subscription route")
    model, = (item for item in route["models"] if item["id"] == selection["model"])
    model["reasoningEfforts"] = {"off": None, "high": "high"}
    model.setdefault("compat", {})["thinkingFormat"] = "deepseek"
    route["retryPolicy"] = {"mode": "normal", "maxRetries": 0}
    selection["reasoningEffort"] = "off"
    return entries


def main():
    import yaml
    system, user = messages(json.load(sys.stdin))
    # Dsh receives the trusted host rules in its system prompt. Phone text is stdin data.
    with TemporaryDirectory() as directory:
        patch = Path(directory) / "instructions.yml"
        patch.write_text(json.dumps([{"id": "system-prompt", "config": {"personaPrefix": system}}], ensure_ascii=False))
        provider = Path(directory) / "provider.yml"
        provider.write_text(json.dumps(planning_provider(yaml.safe_load(Path(PROVIDER).read_bytes()))))
        cmd = [BINARY, "--profile", "headless", "--patch", str(provider), "--patch", str(PROFILE),
               "--patch", str(patch), "--json", "-"]
        process = subprocess.run(cmd, input=user.encode(), cwd=directory, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, check=False)
        result = parse_events(process.stdout.splitlines())
        if process.returncode != 0:
            result["proposal"] = None
            code = re.search(rb"^dsh: ([A-Z][A-Z0-9_]{1,63}):", process.stderr, re.M)
            result["failureCode"] = code[1].decode("ascii") if code else "NATIVE_ERROR"
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
