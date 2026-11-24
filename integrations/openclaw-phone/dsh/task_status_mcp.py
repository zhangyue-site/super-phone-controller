"""Expose the authenticated status of the supervisor's single task to Dsh over stdio."""
import importlib.util
import json
import re
import sys
from pathlib import Path

BRIDGE = Path("/opt/phone-agent/phone_mcp.py")


def main(task_id):
    if not re.fullmatch(r"[a-f0-9]{32}", task_id):
        raise ValueError("invalid task binding")
    spec = importlib.util.spec_from_file_location("phone_bridge", BRIDGE)
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)

    def status(args):
        if args:
            raise ValueError("status takes no arguments")
        record = bridge._authorized_status(task_id)
        if record.get("task_id") != task_id:
            raise ValueError("status binding changed")
        return json.dumps({field: record.get(field) for field in
                           ("state", "terminal", "verified", "observedAt")})

    def progress(args):
        if args:
            raise ValueError("progress takes no arguments")
        record = bridge._authorized_status(task_id)
        if record.get("task_id") != task_id:
            raise ValueError("progress binding changed")
        root = bridge.STATE / "agent-runs"
        result_path = root / (task_id + "-result.json")
        if not result_path.is_file():
            return json.dumps({"resultAvailable": False})
        result = json.loads(result_path.read_bytes())
        events = result.get("events", [])
        actions = {event["action_id"]: event["capability"] for event in events if event["event"] == "action_intent"}
        receipts = [{"action": actions[e["action_id"]], "status": e["status"]} for e in events
                    if e["event"] == "receipt" and e["action_id"] in actions]
        doctor = result.get("doctor") or {}
        return json.dumps({"resultAvailable": True, "actionIntents": len(actions), "receipts": receipts,
                           "verified": result.get("verified") is True,
                           "failureComponent": doctor.get("component"), "failureCode": doctor.get("code")})

    schema = dict(type="object", properties={}, additionalProperties=False)
    bridge.TOOLS = [
        dict(name="task_status", description="读取本次已确认任务的即时状态。", inputSchema=schema),
        dict(name="task_progress", description="核对同一任务的动作数、设备回执与诊断。", inputSchema=schema),
    ]
    bridge.HANDLERS = {"task_status": status, "task_progress": progress}
    bridge.main()


if __name__ == "__main__":
    main(sys.argv[1])
