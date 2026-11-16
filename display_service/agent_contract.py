"""Pure agent contracts. No model output is permission and no actuator is imported.

Authority and guard must be supplied by the trusted mailbox/lease adapter, never
constructed from model JSON. begin_action only reserves an audited intent; the
adapter must still apply its own current-frame, live consent and HID fences.
"""
import copy
import math
import time
from dataclasses import dataclass

PHASES = ("understand", "observe", "plan", "execute", "verify", "learn")
TERMINAL = frozenset(("done", "stopped", "timed_out"))


def _text(value):
    return isinstance(value, str) and 0 < len(value.strip()) <= 512


def _keys(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError("contract fields")


@dataclass(frozen=True)
class Capability:
    """Trusted capability registry entry; arbitrary names need explicit support."""
    effect: str

    def __post_init__(self):
        if self.effect not in ("observe", "navigate", "write"):
            raise ValueError("capability effect")


@dataclass(frozen=True)
class Authority:
    goal_id: str
    device: str
    session: str
    lease: str
    capabilities: frozenset
    expires: float

    def __post_init__(self):
        if not all(_text(v) for v in (self.goal_id, self.device, self.session, self.lease)):
            raise ValueError("authority binding")
        if not isinstance(self.capabilities, frozenset) or not all(_text(v) for v in self.capabilities):
            raise ValueError("authority capabilities")
        if type(self.expires) not in (int, float) or not math.isfinite(self.expires):
            raise ValueError("authority expiry")


def validate_goal(value, capabilities):
    _keys(value, ("id", "objective", "app", "capabilities", "constraints", "success", "ambiguities", "budget"))
    if not all(_text(value[k]) for k in ("id", "objective", "app")):
        raise ValueError("goal identity")
    for key in ("capabilities", "constraints", "success", "ambiguities"):
        rows = value[key]
        if not isinstance(rows, list) or len(rows) > 32 or not all(_text(v) for v in rows) or len(set(rows)) != len(rows):
            raise ValueError("goal list")
    if not value["capabilities"] or not value["success"]:
        raise ValueError("goal missing capability or completion criterion")
    if any(name not in capabilities or not isinstance(capabilities[name], Capability) for name in value["capabilities"]):
        raise ValueError("unsupported capability")
    _keys(value["budget"], ("actions", "model_calls", "replans", "seconds"))
    limits = dict(actions=64, model_calls=64, replans=16, seconds=600)
    for key, maximum in limits.items():
        n = value["budget"][key]
        if type(n) is not int or not (0 if key == "replans" else 1) <= n <= maximum:
            raise ValueError("invalid budget")
    return copy.deepcopy(value)


def validate_plan(value, goal, capabilities):
    goal = validate_goal(goal, capabilities)
    if not isinstance(value, list) or not 1 <= len(value) <= 4:
        raise ValueError("bounded plan required")
    for row in value:
        _keys(row, ("capability", "target"))
        if row["capability"] not in goal["capabilities"] or not _text(row["target"]):
            raise ValueError("plan outside goal")
    return copy.deepcopy(value)


class AgentRun:
    """Six-phase audit state; methods do not execute physical actions.

    Receipts and evidence are supplied by trusted adapters. Failed/unknown
    receipts terminate every effect, including writes; no automatic replay.
    """
    def __init__(self, goal, capabilities, authority, *, guard, clock=time.monotonic):
        self._caps = dict(capabilities)
        self._goal = validate_goal(goal, self._caps)
        if not isinstance(authority, Authority) or not callable(guard):
            raise ValueError("trusted authority and live guard required")
        self.authority = authority
        self.guard = guard
        self.clock = clock
        self.started = clock()
        self.state = "understand"
        self._events = []
        self._plan = []
        self._pending = None
        self._used = set()
        self._verified = False
        self._last_action = self.started
        self._counts = dict(actions=0, model_calls=0, replans=0)
        self._log("created")

    @property
    def goal(self):
        return copy.deepcopy(self._goal)

    @property
    def events(self):
        return copy.deepcopy(self._events)

    @property
    def learnable(self):
        return self.state == "done" and self._verified

    def _log(self, event, **data):
        self._events.append(dict(seq=len(self._events)+1, phase=self.state, event=event,
                                 elapsed_ms=max(0, int((self.clock()-self.started)*1000)), **data))

    def stop(self, reason="user_stop"):
        if self.state not in TERMINAL:
            self.state = "stopped"
            self._verified = False
            self._log("stopped", reason=reason[:80])

    def _live(self):
        if self.state in TERMINAL:
            raise ValueError("terminal run")
        if self.clock()-self.started >= self._goal["budget"]["seconds"]:
            self.state = "timed_out"
            self._verified = False
            self._log("timeout", pending_action=self._pending[0] if self._pending else None)
            raise TimeoutError("agent budget expired; no retry")

    def _authorized(self, capability=None):
        self._live()
        a = self.authority
        try:
            valid = a.goal_id == self._goal["id"] and self.clock() < a.expires and self.guard(a) is True
        except Exception:
            valid = False
        if not valid or capability is not None and capability not in a.capabilities:
            self.stop("authority_invalid")
            raise ValueError("external authority missing or revoked")

    def charge(self, resource):
        self._live()
        if resource not in self._counts:
            raise ValueError("budget resource")
        if self._counts[resource] >= self._goal["budget"][resource]:
            self.stop("budget_"+resource)
            raise ValueError("agent budget exhausted")
        self._counts[resource] += 1
        self._log("budget", resource=resource, used=self._counts[resource])

    def advance(self, phase):
        self._live()
        normal = PHASES[PHASES.index(self.state)+1] if self.state != "learn" else None
        replan = self.state == "verify" and phase == "observe" and not self._verified
        if self._pending or phase != normal and not replan:
            raise ValueError("invalid phase transition")
        if phase == "execute" and (not self._plan or self._goal["ambiguities"]):
            raise ValueError("unresolved goal or missing plan")
        if phase == "learn" and not self._verified:
            raise ValueError("completion evidence required")
        if replan:
            self._plan = []
        self.state = phase
        self._log("phase")

    def reobserve(self, reason):
        self._authorized("observe")
        if self.state!="plan" or self._pending:
            raise ValueError("reobserve only before an action")
        self.charge("replans")
        self._plan=[];self.state="observe"
        self._log("reobserve",reason=str(reason)[:160])

    def set_plan(self, steps):
        self._live()
        if self.state != "plan":
            raise ValueError("planning phase required")
        self._plan = validate_plan(steps, self._goal, self._caps)
        self._used.clear()
        self._log("plan", capabilities=[r["capability"] for r in self._plan])

    def begin_action(self, index):
        self._live()
        if self.state != "execute" or self._pending or type(index) is not int or not 0 <= index < len(self._plan) or index in self._used:
            raise ValueError("action not available")
        row = self._plan[index]
        self._authorized(row["capability"])
        self.charge("actions")
        ident = "action-"+str(self._counts["actions"])
        self._pending = (ident, index)
        self._used.add(index)
        self._last_action = self.clock()
        self._verified = False
        self._log("action_intent", action_id=ident, capability=row["capability"], effect=self._caps[row["capability"]].effect)
        return ident

    def receipt(self, action_id, status):
        self._authorized()
        if not self._pending or self._pending[0] != action_id or status not in ("confirmed", "failed", "unknown"):
            self.stop("receipt_binding_invalid")
            raise ValueError("receipt mismatch")
        self._log("receipt", action_id=action_id, status=status)
        self._pending = None
        if status != "confirmed":
            self.stop("action_"+status)
        else:
            self._last_action = self.clock()

    def verify(self, evidence):
        # The independent snapshot must be captured after the receipt. Model
        # inference latency does not revoke that snapshot; live authority and
        # the total run deadline still apply. This does not authorize inputs.
        self._authorized()
        if self.state != "verify" or self._pending:
            raise ValueError("verification phase required")
        _keys(evidence, ("goal_id", "session", "frame_id", "observed_at", "source", "verified", "independent", "criteria"))
        stamp = evidence["observed_at"]
        if (evidence["goal_id"] != self._goal["id"] or evidence["session"] != self.authority.session
                or not _text(evidence["frame_id"]) or evidence["source"] != "live_screen"
                or evidence["verified"] is not True or evidence["independent"] is not True
                or type(stamp) not in (int, float) or not math.isfinite(stamp)
                or not self._last_action < stamp <= self.clock()
                or not isinstance(evidence["criteria"], list)
                or evidence["criteria"] != self._goal["success"]):
            raise ValueError("independent fresh completion evidence required")
        self._verified = True
        self._log("verified", frame_id=evidence["frame_id"])

    def finish(self):
        self._authorized()
        if self.state != "learn" or not self._verified or self._pending:
            raise ValueError("verified learning phase required")
        self.state = "done"
        self._log("done")
