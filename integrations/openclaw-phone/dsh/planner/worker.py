"""Translate one text planning request into an isolated native Dsh headless session."""
import json
from pathlib import Path
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
    return system["content"] + "\n" + POLITE, content


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
        try:
            result = json.loads(final.strip().removeprefix("```json").removesuffix("```").strip())
        except ValueError:
            pass
    return {"proposal": result if isinstance(result, dict) else None, "usage": usage}


def main():
    system, user = messages(json.load(sys.stdin))
    # Dsh receives the trusted host rules in its system prompt. Phone text is stdin data.
    with TemporaryDirectory() as directory:
        patch = Path(directory) / "instructions.yml"
        patch.write_text(json.dumps([{"id": "system-prompt", "config": {"personaPrefix": system}}], ensure_ascii=False))
        cmd = [BINARY, "--profile", "headless", "--patch", PROVIDER, "--patch", str(PROFILE),
               "--patch", str(patch), "--json", "-"]
        process = subprocess.run(cmd, input=user.encode(), cwd=directory, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, check=False)
        result = parse_events(process.stdout.splitlines())
        if process.returncode != 0:
            result["proposal"] = None
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
