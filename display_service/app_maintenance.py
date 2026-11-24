"""Latest target-reported Android app update status, scoped to its controlling ticket."""

from datetime import datetime, timezone
import json
import os
import re
import sqlite3
import time



REPORT = "/app-control/maintenance-report"
READ = "/app-control/maintenance-read"
STATES = frozenset((
    "idle", "checking", "current", "available", "downloading", "verifying",
    "ready", "permission_required", "installer_opened", "error",
))
RELEASE_NAME = re.compile(r"(?:0|[1-9][0-9]{0,8})(?:\.(?:0|[1-9][0-9]{0,8})){2}")
REQUIRED = frozenset(("installedCode", "installedName", "state"))


def now_seconds():
    return int(time.time())


def read_fields(handler):
    # Reject duplicate JSON keys as well as unknown ones. The generic command parser
    # intentionally follows normal JSON last-key-wins behavior for its older clients.
    lengths = handler.headers.get_all("Content-Length", [])
    if handler.headers.get("Transfer-Encoding") is not None or len(lengths) > 1:
        raise ValueError("unsupported framing")
    size = int(lengths[0]) if lengths else 0
    if not 0 <= size <= 512:
        raise ValueError("size")
    if size == 0:
        return {}
    raw = handler.rfile.read(size)
    if len(raw) != size:
        raise ValueError("truncated request")

    def distinct(pairs):
        obj = dict(pairs)
        if len(obj) != len(pairs):
            raise ValueError("duplicate field")
        return obj

    obj = json.loads(raw, object_pairs_hook=distinct)
    if not isinstance(obj, dict):
        raise ValueError("object required")
    return obj


def validate(report):
    keys = set(report)
    if keys != REQUIRED and keys != REQUIRED | {"targetCode"}:
        raise ValueError("fields")
    for key in ("installedCode", "targetCode"):
        if key in report and (type(report[key]) is not int or not 1 <= report[key] <= 2147483647):
            raise ValueError("version code")
    if not isinstance(report["installedName"], str) or not RELEASE_NAME.fullmatch(report["installedName"]):
        raise ValueError("release version")
    if not isinstance(report["state"], str) or report["state"] not in STATES:
        raise ValueError("state")


def write(db, device, report, received):
    # Lazy creation also supports pre-existing pairing databases. A read never creates a table.
    with db:
        db.execute("""CREATE TABLE IF NOT EXISTS app_maintenance (
            device TEXT PRIMARY KEY, installed_code INTEGER NOT NULL, installed_name TEXT NOT NULL,
            state TEXT NOT NULL, target_code INTEGER, received INTEGER NOT NULL)""")
        db.execute("""INSERT INTO app_maintenance
            (device, installed_code, installed_name, state, target_code, received)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(device) DO UPDATE SET installed_code=excluded.installed_code,
            installed_name=excluded.installed_name, state=excluded.state,
            target_code=excluded.target_code, received=excluded.received""",
            (device, report["installedCode"], report["installedName"], report["state"],
             report.get("targetCode"), received))


def read(db, device, now):
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='app_maintenance'").fetchone()
    if not exists:
        return None
    row = db.execute("""SELECT installed_code, installed_name, state, target_code, received
                        FROM app_maintenance WHERE device=?""", (device,)).fetchone()
    if row is None:
        return None
    code, name, state, target, received = row
    result = {"installedCode": code, "installedName": name, "state": state,
              "receivedAt": datetime.fromtimestamp(received, timezone.utc).isoformat().replace("+00:00", "Z"),
              "ageSeconds": max(0, now - received)}
    if target is not None:
        result["targetCode"] = target
    return result


def handle(handler):
    path = handler.path
    if path not in (REPORT, READ):
        return False
    # Import lazily: the two modules share the live authorization and pairing objects.
    from . import app_control as authority
    status, result = 200, {}
    if handler.command != "POST":
        status = 405
    elif os.environ.get("EPAPER_REMOTE_CONTROL") != "1":
        status = 503
    else:
        try:
            ticket = authority.bearer(handler)
            obj = read_fields(handler)
            pairings = authority.PAIRINGS
            # The authority changes parents under SESSION_LOCK. The pairing store uses its
            # own RLock for credential revocation and access to the shared sqlite connection.
            with authority.SESSION_LOCK, pairings.lock:
                if path == REPORT:
                    device = authority.owner(ticket)[3]
                    validate(obj)
                    write(pairings.db, device, obj, now_seconds())
                    result = {"accepted": True}
                else:
                    device = authority.controller_owner(ticket)[3]
                    if obj:
                        raise ValueError("empty body required")
                    result = {"appMaintenance": read(pairings.db, device, now_seconds())}
        except PermissionError:
            status = 403
        except (ValueError, TypeError):
            status = 400
        except (OSError, sqlite3.Error):
            status = 503
    handler.reply(status, json.dumps(result).encode())
    return True
