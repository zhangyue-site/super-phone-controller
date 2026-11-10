"""Ephemeral on-device recognition for the currently authorized screen grant.

Callers hold the screen authority lock. Results never enter a model prompt or
the job mailbox. A heartbeat can expire an observation but cannot freshen it.
"""
import re

MAX_AGE = 12
HEARTBEAT_AGE = 5
MAX_BODY = 8192
STATES = {"running", "done", "frame_timeout", "inference_timeout", "timeout", "error"}


def _identifier(value, pattern):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


class LocalScreenResults:
    def __init__(self):
        self.entries = {}

    def discard(self, ticket):
        self.entries.pop(ticket, None)

    def record(self, ticket, device, grants, now, unlocked, payload):
        for previous in tuple(self.entries):
            if previous not in grants:
                self.discard(previous)
        old = self.entries.pop(ticket, None)
        grant = grants.get(ticket)
        if not unlocked or not grant or grant[0] <= now or grant[1] != device:
            return []
        if (not isinstance(payload, dict) or set(payload) != {"v", "platform", "results"} or
                type(payload["v"]) is not int or payload["v"] != 1 or
                payload["platform"] not in ("android", "ios") or
                not isinstance(payload["results"], list) or len(payload["results"]) > 2):
            raise ValueError("recognition payload")
        current = {}
        epochs = set()
        for row in payload["results"]:
            if not isinstance(row, dict) or row.get("source") not in ("ocr", "buttons"):
                raise ValueError("recognition source")
            source = row["source"]
            field = "text" if source == "ocr" else "boxes"
            if (set(row) != {"run", "epoch", "frame", "source", "count", "state", "ageMs", field} or
                    source in current or not _identifier(row["run"], "[0-9a-f]{32}") or
                    not _identifier(row["epoch"], "[1-9][0-9]{0,18}") or
                    not _identifier(row["frame"], "[1-9][0-9]{0,18}") or
                    type(row["count"]) is not int or not 1 <= row["count"] <= 10 or
                    type(row["ageMs"]) is not int or not 0 <= row["ageMs"] <= MAX_AGE * 1000 or
                    not isinstance(row["state"], str) or row["state"] not in STATES or
                    (row["state"] == "done" and row["count"] != 10)):
                raise ValueError("recognition evidence")
            if field == "text" and (not isinstance(row[field], str) or len(row[field]) > 480):
                raise ValueError("recognition text")
            if field == "boxes" and (type(row[field]) is not int or not 0 <= row[field] <= 2100):
                raise ValueError("recognition boxes")
            epochs.add(row["epoch"])
            expires = now + MAX_AGE - row["ageMs"] / 1000
            previous = old[1].get(source) if old else None
            if previous:
                prior, prior_expiry = previous
                if row["epoch"] != prior["epoch"] or int(row["frame"]) < int(prior["frame"]):
                    raise ValueError("obsolete recognition frame")
                if row["frame"] == prior["frame"]:
                    if any(row[key] != prior[key] for key in ("run", "count", field)):
                        raise ValueError("changed recognition frame")
                    expires = min(expires, prior_expiry)
            current[source] = (row, expires)
        if len(epochs) > 1:
            raise ValueError("mixed recognition sessions")
        if current:
            self.entries[ticket] = (now, current)
        return [{key: row[key] for key in ("source", "run", "epoch", "frame", "count", "state")}
                for row, _ in current.values()]

    def read(self, device, grants, now):
        tickets = [ticket for ticket, grant in grants.items() if grant[0] > now and grant[1] == device]
        entry = self.entries.get(tickets[0]) if len(tickets) == 1 else None
        if not entry or not 0 <= now - entry[0] <= HEARTBEAT_AGE:
            return []
        return [row for row, expires in entry[1].values() if now < expires]
