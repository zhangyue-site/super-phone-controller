"""Immutable observation envelopes and same-value remapping. No device or model IO.

Only the trusted runtime calls capture after fresh(). observed_at is the local
observation time, not an invented phone capture timestamp. External model JSON
cannot supply binding metadata or authorize input.
"""
import copy
import hashlib
import json
import math
from dataclasses import dataclass
from .agent_contract import Authority
from .agent_gates import GateError


def _error(code, message, recovery="reobserve"):
    return GateError(code, "observation", recovery, message)


def _dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_dump(value).encode()).hexdigest()


@dataclass(frozen=True)
class Snapshot:
    _identity_json: str
    _hint_json: str
    observed_at: float

    def identity(self):
        return json.loads(self._identity_json)

    def hint(self):
        return dict(json.loads(self._hint_json), _observation=self.identity())

    def require_current(self, authority, *, now, max_age=2.5):
        identity = self.identity()
        if not _authority_matches(identity, authority):
            raise _error("observation_binding_changed", "任务或共享会话改变，旧观察不可执行。")
        if (type(now) not in (int, float) or not math.isfinite(now)
                or not 0 <= now-self.observed_at <= max_age):
            raise _error("observation_stale", "观察已过期，请重新获取真实画面。")
        return self


def _authority_matches(identity, authority):
    return isinstance(authority, Authority) and all(identity[k] == v for k, v in (
        ("task_id", authority.goal_id), ("device_id", authority.device),
        ("capture_session", authority.session), ("binding_id", _digest(authority.lease))))


def capture(authority, sequence, raw, hint, *, observed_at, rotation=None):
    if (not isinstance(authority, Authority) or type(sequence) is not int or sequence < 1
            or not isinstance(raw, bytes) or not raw or not isinstance(hint, dict)
            or type(observed_at) not in (int, float) or not math.isfinite(observed_at)
            or rotation not in (None, 0, 90, 180, 270)):
        raise _error("observation_invalid", "观察身份或时间无效。", "stop")
    clean = {k: copy.deepcopy(v) for k, v in hint.items() if k != "_observation"}
    w, h = clean.get("width"), clean.get("height")
    lines = clean.get("lines")
    if (type(w) is not int or type(h) is not int or not 1 <= w <= 4096 or not 1 <= h <= 4096
            or not isinstance(lines, list) or len(lines) > 64):
        raise _error("observation_invalid", "观察几何或OCR格式无效。", "stop")
    for row in lines:
        b = row.get("bounds") if isinstance(row, dict) else None
        if (not isinstance(row, dict) or not isinstance(row.get("text"), str)
                or not isinstance(b, list) or len(b) != 4 or any(type(n) is not int for n in b)
                or not 0 <= b[0] < b[2] <= w or not 0 <= b[1] < b[3] <= h):
            raise _error("observation_invalid", "OCR行或坐标无效。", "stop")
    image_hash = hashlib.sha256(raw).hexdigest()
    identity = dict(schema_version=1, task_id=authority.goal_id, device_id=authority.device,
                    capture_session=authority.session, binding_id=_digest(authority.lease),
                    frame_id=str(sequence)+":"+image_hash, image_sha256=image_hash,
                    geometry=dict(width=w, height=h, rotation=rotation), ocr_sha256=_digest(lines))
    return Snapshot(_dump(identity), _dump(clean), float(observed_at))


def bind_visual(snapshot, view):
    identity = snapshot.identity() if isinstance(snapshot, Snapshot) else snapshot.get("_observation")
    if not identity:
        raise _error("visual_unbound", "图像识别缺少观察身份。", "observe_image")
    if (not isinstance(view, dict) or set(view) - {"scene", "widgets", "regions"}
            or not isinstance(view.get("scene"), str)):
        raise _error("visual_invalid", "图像模型不得提供动作或帧身份。", "observe_image")
    out = copy.deepcopy(view)
    geometry = identity["geometry"]
    for key in ("widgets", "regions"):
        rows = out.setdefault(key, [])
        if not isinstance(rows, list) or len(rows) > 64:
            raise _error("visual_invalid", "图像识别结构无效。", "observe_image")
        for row in rows:
            b = row.get("bounds") if isinstance(row, dict) else None
            if (not isinstance(b, list) or len(b) != 4 or any(type(n) is not int for n in b)
                    or not 0 <= b[0] < b[2] <= geometry["width"]
                    or not 0 <= b[1] < b[3] <= geometry["height"]):
                raise _error("visual_invalid", "图像识别坐标无效。", "observe_image")
    out["observation"] = copy.deepcopy(identity)
    return out


def current_visual(hint, visual):
    if (not isinstance(visual, dict) or not hint.get("_observation")
            or visual.get("observation") != hint["_observation"]):
        raise _error("visual_frame_mismatch", "图像框不属于当前观察帧，请重新识别。", "observe_image")
    return copy.deepcopy(visual)


def rebind_identical_visual(visual, old, new):
    current_visual(old.hint(), visual)
    before, after = old.identity(), new.identity()
    if any(before[k] != after[k] for k in ("task_id", "device_id", "capture_session", "binding_id", "geometry", "image_sha256", "ocr_sha256")):
        raise _error("visual_frame_mismatch", "新画面发生变化，旧图像框不可沿用。", "observe_image")
    view = {k: visual[k] for k in ("scene", "widgets", "regions")}
    return bind_visual(new, view)


def remap_rows(data, original, current, *, matcher=None):
    a, b = original.identity(), current.identity()
    if any(a[k] != b[k] for k in ("task_id", "device_id", "capture_session", "binding_id", "geometry")):
        raise _error("observation_binding_changed", "帧引用的任务、会话或几何已改变。")
    if (not isinstance(data, dict) or set(data) != {"values", "rows"}
            or not isinstance(data["values"], dict) or not data["values"]
            or not isinstance(data["rows"], dict) or set(data["values"]) != set(data["rows"])):
        raise _error("ocr_reference_invalid", "OCR字段引用结构无效。", "stop")
    old_lines, new_lines = original.hint()["lines"], current.hint()["lines"]
    matcher = matcher or (lambda key, raw, value: raw == value)
    rows = {}
    for key, value in data["values"].items():
        index = data["rows"][key]
        if (type(index) is not int or not 0 <= index < len(old_lines)
                or not matcher(key, old_lines[index]["text"], value)
                or sum(bool(matcher(key, row["text"], value)) for row in old_lines) != 1):
            raise _error("ocr_reference_invalid", "原帧OCR索引与字段不一致或不唯一。", "stop")
        hits = [i for i, row in enumerate(new_lines) if matcher(key, row["text"], value)]
        if len(hits) != 1:
            raise _error("ocr_target_ambiguous" if hits else "ocr_target_missing", "新帧字段未唯一定位，未执行输入。")
        rows[key] = hits[0]
    return dict(values=copy.deepcopy(data["values"]), rows=rows)


def rebind_visual_region(visual, old, new, raw_before, raw_after, bounds):
    """Revalidate one unchanged ROI plus independent OCR context on a later frame.

    Decoded target pixels must be identical; no perceptual threshold is used.
    At least two unique non-status OCR anchors must retain their positions.
    Task, device, capture, authority and geometry bindings remain mandatory.
    Neither stale coordinates nor changed target pixels can be transferred.
    """
    import io
    import re
    from PIL import Image
    current_visual(old.hint(), visual)
    a,b=old.identity(),new.identity()
    if any(a[k]!=b[k] for k in ("task_id","device_id","capture_session","binding_id","geometry")):
        raise _error("visual_frame_mismatch","视觉目标的会话或几何已改变。","observe_image")
    if hashlib.sha256(raw_before).hexdigest()!=a["image_sha256"] or hashlib.sha256(raw_after).hexdigest()!=b["image_sha256"]:
        raise _error("visual_frame_mismatch","图像内容与观察身份不一致。","observe_image")
    if a["image_sha256"]==b["image_sha256"]:
        if a["ocr_sha256"]==b["ocr_sha256"]:return rebind_identical_visual(visual,old,new)
        # Native OCR may reorder identical rows; order has no visual meaning.
        ordered=lambda snapshot:sorted(_dump(row) for row in snapshot.hint()["lines"])
        if ordered(old)==ordered(new):return bind_visual(new,{key:visual[key] for key in ("scene","widgets","regions")})
    w,h=a["geometry"]["width"],a["geometry"]["height"]
    if (not isinstance(bounds,list) or len(bounds)!=4 or any(type(v)is not int for v in bounds)
            or not 0<=bounds[0]<bounds[2]<=w or not 0<=bounds[1]<bounds[3]<=h):
        raise _error("visual_target_missing","没有可重新验证的目标区域。","observe_image")
    # The target itself remains pixel-exact. Dynamic content elsewhere must not
    # turn a stable control into a coordinate replay; independent page anchors
    # still bind the target to the same visible page and geometry.
    def anchors(snapshot):
        values={}
        for row in snapshot.hint()["lines"]:
            x1,y1,x2,y2=row["bounds"]
            if y2<=h*.075:continue
            values.setdefault(row["text"],[]).append(((x1+x2)/2,(y1+y2)/2))
        return {label:points[0] for label,points in values.items() if len(points)==1}
    before,after=anchors(old),anchors(new)
    shared=[label for label,point in before.items() if label in after
            and abs(point[0]-after[label][0])<=max(2,w*.005)
            and abs(point[1]-after[label][1])<=max(2,h*.005)]
    if len(shared)<2:
        raise _error("visual_context_changed","当前页面缺少两个稳定独立锚点，请重新观察。","observe_image")
    try:
        with Image.open(io.BytesIO(raw_before)) as left,Image.open(io.BytesIO(raw_after)) as right:
            same=left.size==right.size==(w,h)
            if same:same=left.convert("RGB").crop(tuple(bounds)).tobytes()==right.convert("RGB").crop(tuple(bounds)).tobytes()
    except (ValueError,OSError):same=False
    if not same:raise _error("visual_target_changed","当前操作目标区域像素发生变化，请重新识别。","observe_image")
    view=dict(scene=visual["scene"],widgets=[r for r in visual["widgets"] if r["bounds"]==bounds],regions=[r for r in visual["regions"] if r["bounds"][0]<=bounds[0]<bounds[2]<=r["bounds"][2] and r["bounds"][1]<=bounds[1]<bounds[3]<=r["bounds"][3]])
    if not view["widgets"] and not view["regions"]:
        raise _error("visual_target_missing","目标区域没有原帧识别依据。","observe_image")
    return bind_visual(new,view)
