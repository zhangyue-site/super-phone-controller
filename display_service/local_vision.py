"""Paired-controller observations only. This module never issues phone actions."""
import base64
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
from . import app_control, app_screen, remote_http

MAX_MODEL = 32 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{64}\Z")

def _model(path=None):
    path = path or os.environ.get("CONTROLLER_LOCAL_MODEL_MANIFEST")
    if not path:
        return None
    manifest = Path(path)
    if manifest.stat().st_size > 8192:
        raise ValueError("manifest size")
    obj = json.loads(manifest.read_text())
    if not isinstance(obj, dict):
        raise ValueError("manifest object")
    sha, size = obj.get("sha256"), obj.get("size")
    if not isinstance(sha, str) or not SHA.fullmatch(sha) or type(size) is not int or not 0 < size <= MAX_MODEL:
        raise ValueError("model identity")
    if obj.get("file") != sha + ".onnx" or obj.get("format") != "onnx" or not isinstance(obj.get("version"), str) or not 1 <= len(obj["version"]) <= 128:
        raise ValueError("model format")
    if any(k in obj for k in ("url", "downloadUrl", "download_url")):
        raise ValueError("external model")
    file = manifest.parent / obj["file"]
    if file.is_symlink() or not file.is_file() or file.stat().st_size != size:
        raise ValueError("model size")
    with file.open("rb") as stream:
        payload = stream.read(MAX_MODEL + 1)
    if len(payload) != size or hashlib.sha256(payload).hexdigest() != sha:
        raise ValueError("model digest")
    public = dict(available=True, format="onnx", version=obj["version"], sha256=sha, size=size,
                  inputWidth=320, inputHeight=320, outputLayout="xywh-score", preprocess="stretch-rgb-0-1")
    return public, payload

def model_manifest(path=None):
    model = _model(path)
    return model[0] if model else {"available": False}

def _number(value, lower, upper):
    return type(value) in (int, float) and math.isfinite(value) and lower <= value <= upper

def validate_result(obj):
    if set(obj) != {"task_id", "frame_id", "barrier", "sequence", "model_sha256", "boxes", "inference_ms"}:
        raise ValueError("result fields")
    if type(obj["sequence"]) is not int or not 1 <= obj["sequence"] <= 2147483647:
        raise ValueError("sequence")
    if not _number(obj["inference_ms"], 0, 3600000):
        raise ValueError("inference timing")
    boxes = obj["boxes"]
    if not isinstance(boxes, list) or len(boxes) > 100:
        raise ValueError("boxes")
    for box in boxes:
        if not isinstance(box, dict) or set(box) != {"x", "y", "width", "height", "score"} or not all(_number(v, 0, 1) for v in box.values()):
            raise ValueError("box")
        if box["width"] <= 0 or box["height"] <= 0 or box["x"] + box["width"] > 1.000001 or box["y"] + box["height"] > 1.000001:
            raise ValueError("box bounds")

class ObservationUnavailable(PermissionError):
    """Valid controller, but this task or capture is no longer active."""
    pass

class Observations:
    def __init__(self, remote=None):
        self.remote = remote or remote_http.REMOTE

    def access(self, ticket, task_id, operation):
        identity = app_control.PAIRINGS.owner(ticket)
        return self._access_identity(identity, task_id, operation)

    def _access_identity(self, identity, task_id, operation):
        if not isinstance(task_id, str) or not re.fullmatch(r"[0-9a-f]{32}", task_id):
            raise ValueError("task")
        remote = self.remote
        mailbox = remote.c.mailbox
        # Matches remote task -> capture authority -> mailbox order. Parent
        # authorization is rechecked on every read, submit and hint consumption.
        with remote.lock, app_screen.AUTHORITY.lock, mailbox.lock:
            if not app_control.PAIRINGS.allowed(identity):
                raise PermissionError("revoked")
            _, record = remote._get(identity, task_id)
            job = remote.jobs.get(task_id)
            if record["state"] != "running" or job is None or mailbox.jobs.get(identity[3]) is not job:
                raise ObservationUnavailable("inactive task")
            mailbox._live(job)
            if job.done or job.cancelled or getattr(job, "remote_task_id", None) != task_id or (job.session, job.sequence) != (record.get("session"), record.get("sequence")):
                raise ObservationUnavailable("inactive turn")
            capture = app_screen.AUTHORITY.tickets.get(job.screen_session)
            if not job.screen_session and not job.video:
                capture = next((item for item in app_screen.AUTHORITY.tickets.values()
                                if item[0] > app_screen.AUTHORITY.clock() and item[1] == identity[3]), None)
            if capture is None or capture[0] <= app_screen.AUTHORITY.clock() or capture[1] != identity[3]:
                raise ObservationUnavailable("capture revoked")
            fresh = bool(job.video and job.video_source == "user-consented-app-screen" and 0 <= mailbox.clock() - job.video_received <= 2)
            return operation(job, fresh)

    def frame(self, ticket, task_id):
        def read(job, fresh):
            if not fresh:
                return {"task_id": task_id, "state": "waiting"}
            job.local_vision_issued = (hashlib.sha256(job.video).hexdigest(), job.video_barrier, job.video_sequence, job.video_received)
            return dict(task_id=task_id, frame_id=hashlib.sha256(job.video).hexdigest(), barrier=job.video_barrier,
                        sequence=job.video_sequence, width=job.video_width, height=job.video_height,
                        jpegBase64=base64.b64encode(job.video).decode("ascii"))
        return self.access(ticket, task_id, read)

    def submit(self, ticket, obj):
        validate_result(obj)
        model = _model()
        if model is None or obj["model_sha256"] != model[0]["sha256"]:
            raise ValueError("model changed")
        def accept(job, fresh):
            issued = getattr(job, "local_vision_issued", None)
            if obj["sequence"] != job.video_sequence or issued != (obj["frame_id"], obj["barrier"], obj["sequence"], job.video_received):
                raise ValueError("unissued frame")
            if not fresh or obj["frame_id"] != hashlib.sha256(job.video).hexdigest() or obj["barrier"] != job.video_barrier:
                raise ValueError("stale frame")
            job.local_vision_owner = tuple(app_control.PAIRINGS.owner(ticket))
            job.local_vision_hint = copy.deepcopy(obj)
            job.local_vision_hint_sequence = job.video_sequence
            return {"accepted": True, "task_id": obj["task_id"], "frame_id": obj["frame_id"]}
        return self.access(ticket, obj["task_id"], accept)

    def hints(self, ticket, task_id, frame_id, barrier):
        """Read-only planner integration; callers must retain normal HID gates."""
        # Verify bytes before taking task/capture/mailbox locks. Keep only the
        # digest of this verified immutable bytes snapshot for comparison.
        model = _model()
        model_sha = model[0]["sha256"] if model else None
        def read(job, fresh):
            hint = getattr(job, "local_vision_hint", None)
            if getattr(job, "local_vision_hint_sequence", None) != job.video_sequence:
                return None
            if not fresh or not hint or frame_id != hashlib.sha256(job.video).hexdigest() or barrier != job.video_barrier:
                return None
            if not model_sha or hint["model_sha256"] != model_sha or hint["frame_id"] != frame_id or hint["barrier"] != barrier:
                return None
            result = copy.deepcopy(hint)
            return result if 0 <= self.remote.c.mailbox.clock() - job.video_received <= 2 else None
        return self.access(ticket, task_id, read)

    def planner_hints(self, job, frame_bytes):
        """Return geometry for this exact live planning frame, or no hint.

        Stores only the original paired owner identity, never the raw ticket.
        This does not grant action authority or imply semantic button identity.
        """
        identity = getattr(job, "local_vision_owner", None)
        task_id = getattr(job, "remote_task_id", None)
        if identity is None or not isinstance(frame_bytes, bytes):
            return None
        def read(current, fresh):
            hint = getattr(current, "local_vision_hint", None)
            if current is not job or not fresh or not hint or current.video != frame_bytes:
                return None
            if hint["task_id"] != task_id or hint["frame_id"] != hashlib.sha256(frame_bytes).hexdigest():
                return None
            if hint["barrier"] != current.video_barrier or hint["sequence"] != current.video_sequence:
                return None
            if not model_sha or model_sha != hint["model_sha256"]:
                return None
            result = copy.deepcopy(hint)
            return result if 0 <= self.remote.c.mailbox.clock() - current.video_received <= 2 else None
        try:
            model = _model()
            model_sha = model[0]["sha256"] if model else None
            return self._access_identity(identity, task_id, read)
        except (PermissionError, ValueError, TypeError, KeyError, OSError):
            return None

OBSERVATIONS = Observations()

def planner_hints(job, frame_bytes):
    return OBSERVATIONS.planner_hints(job, frame_bytes)

def handle(handler, config=None):
    if handler.path not in ("/app-local-vision/manifest", "/app-local-vision/model", "/app-local-vision/frame", "/app-local-vision/result"):
        return False
    try:
        if handler.command != "POST":
            handler.reply(405, b"{}"); return True
        if os.environ.get("EPAPER_REMOTE_CONTROL") != "1":
            handler.reply(503, b"{}"); return True
        ticket = app_control.bearer(handler)
        app_control.PAIRINGS.owner(ticket)  # Never accept target-only capabilities.
        obj = remote_http.body(handler, 32768)
        route = handler.path.rsplit("/", 1)[1]
        if route == "manifest":
            if obj: raise ValueError("fields")
            result = model_manifest()
        elif route == "model":
            if set(obj) != {"sha256"}: raise ValueError("fields")
            model = _model()
            if not model or obj["sha256"] != model[0]["sha256"]: raise ValueError("model identity")
            app_control.PAIRINGS.owner(ticket)
            handler.reply(200, model[1], "application/octet-stream"); return True
        elif route == "frame":
            if set(obj) != {"task_id"}: raise ValueError("fields")
            result = OBSERVATIONS.frame(ticket, obj["task_id"])
        else:
            result = OBSERVATIONS.submit(ticket, obj)
        app_control.PAIRINGS.owner(ticket)
        handler.reply(202 if result.get("state") == "waiting" else 200, json.dumps(result).encode())
    except ObservationUnavailable:
        handler.reply(409, json.dumps(dict(error="local observation inactive")).encode())
    except PermissionError:
        handler.reply(403, json.dumps(dict(error="controller authorization invalid")).encode())
    except (ValueError, TypeError, KeyError):
        handler.reply(409, json.dumps(dict(error="local observation invalid or stale")).encode())
    except OSError:
        handler.reply(503, json.dumps(dict(error="private model unavailable")).encode())
    return True
