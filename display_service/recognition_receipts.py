"""Bounded read-only recognition receipts, called only after screen-ticket auth."""
import json
import re
import threading

_LOCK = threading.RLock()
_RUNS = {}
STATES = frozenset(("running","done","stopped","closed","capture_changed","locked",
                    "frame_timeout","inference_timeout","timeout","error"))

def receive(device, capture_session, headers):
    values = headers.get_all("X-Pcflash-Recognition", [])
    if len(values) != 1 or len(values[0]) > 4096:
        return None
    try:
        value = json.loads(values[0])
        if not isinstance(value, dict) or set(value) != {"v","run","source","epoch","state","frames"}:
            return None
        if type(value["v"]) is not int or value["v"] != 1:
            return None
        run, source, epoch, state, frames = (value[k] for k in ("run","source","epoch","state","frames"))
        if not isinstance(run,str) or not re.fullmatch("[a-f0-9]{32}",run):
            return None
        if source not in ("ocr","buttons") or state not in STATES:
            return None
        if not isinstance(epoch,str) or not re.fullmatch("[0-9]{1,19}",epoch):
            return None
        if not isinstance(frames,list) or len(frames)>10 or (state=="done" and len(frames)!=10):
            return None
        previous = 0
        for row in frames:
            if not isinstance(row,dict) or set(row)!={"frame","age","ms","lines","width","height","page"}:
                return None
            stamp=row["frame"]
            if not isinstance(stamp,str) or not re.fullmatch("[1-9][0-9]{0,18}",stamp) or int(stamp)<=previous:
                return None
            previous=int(stamp)
            limits={"age":(0,2500),"ms":(0,60000),"lines":(0,60000),"width":(1,16384),"height":(1,16384)}
            if any(type(row[k]) is not int or not lo<=row[k]<=hi for k,(lo,hi) in limits.items()):
                return None
            if row["page"] not in ("other","bill","achai","buttons"):
                return None
        key=(device,run)
        with _LOCK:
            old=_RUNS.get(key)
            if old:
                if old["session"]!=capture_session or old["source"]!=source or old["epoch"]!=epoch:
                    return None
                common=min(len(old["frames"]),len(frames))
                if old["frames"][:common]!=frames[:common]:
                    return None
                if len(frames)<len(old["frames"]) or old["state"]!="running":
                    return {"run":run,"count":len(old["frames"]),"state":old["state"]}
            changed=not old or old["frames"]!=frames or old["state"]!=state
            _RUNS[key]={"session":capture_session,"source":source,"epoch":epoch,"state":state,"frames":frames}
            if len(_RUNS)>128:
                _RUNS.pop(next(iter(_RUNS)))
            if changed:
                print("RECOGNITION_RUN "+json.dumps(dict(device=device,run=run,source=source,
                      state=state,count=len(frames),frames=frames),separators=(",",":")),flush=True)
            return {"run":run,"count":len(frames),"state":state}
    except (ValueError,TypeError,KeyError,OverflowError):
        return None
