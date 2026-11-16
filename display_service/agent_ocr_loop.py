"""Pure OCR navigation experience, never an actuator or a source of authority.

A trusted adapter supplies observations from fresh phone_ocr.frame_hint output.
It must bind source JPEG/session/lease, apply its normal latest-frame HID fence,
and recheck external per-action policy before dispatching a proposed hit.
Two independent model-verified runs are required. Entries contain text semantics,
not coordinates, frames or image crops. Only the returned one-use hit contains
bounds freshly located in the current observation. Writes never enter here.
"""
import copy
import re
import time
import uuid
from dataclasses import dataclass

_FORBIDDEN = re.compile(
    r"保存|记账|记入|录入|确认|确定|同意|允许|接受|继续|下一步|提交|发送|支付|付款|"
    r"转账|购买|充值|授权|权限|登录|删除|清空|清理|清除|安装|卸载|启用|开通|"
    r"关闭|开启|修改|编辑|添加|新建|切换|绑定|解绑|领取|更新|升级|订阅|取消|停用|开始|点赞|喜欢|收藏|关注|重置|恢复|完成|save|confirm|submit|send|pay|buy|delete|remove|allow|"
    r"permission|sign.?in|install|reset", re.I)
_BLOCKED_PAGE = re.compile(
    r"隐私政策|用户协议|服务协议|是否允许|同意并继续|确认删除|确认支付|"
    r"^(确定|确认|同意|允许|接受|继续|取消|保存|提交|立即付款)$")
_DYNAMIC = re.compile(
    r"^[¥￥$€£][+-]?[0-9,.]+(?:元)?$|^[+-]?[0-9]+(?:[.,][0-9]{1,2})?(?:元)?$|"
    r"^[0-9]{1,4}[-/.年][0-9]{1,2}[-/.月][0-9]{1,2}日?(?:.*)?$|"
    r"^[0-9]{1,2}:[0-9]{2}(?::[0-9]{2})?$|交易时间|订单号|金额|商户|备注|付款方|收款方")
_HEALTH = frozenset(("tap_text", "back"))


def _text(value):
    return isinstance(value,str) and 0<len(value.strip())<=256 and all(ord(c)>=32 for c in value)


def _label(value):
    return re.sub(r"\s+","",value)


@dataclass(frozen=True)
class Binding:
    task_id: str
    device: str
    session: str
    lease: str

    def __post_init__(self):
        if not all(_text(v) for v in (self.task_id,self.device,self.session,self.lease)):
            raise ValueError("live task/device/session/lease binding required")


@dataclass(frozen=True, init=False)
class Observation:
    binding: Binding
    frame_id: str
    captured_at: float
    width: int
    height: int
    lines: tuple
    dynamic_texts: tuple

    def __init__(self,binding,frame_id,captured_at,hint,*,dynamic_texts=()):
        import math
        if not isinstance(binding,Binding) or not _text(frame_id) or type(captured_at) not in (int,float) or not math.isfinite(captured_at):
            raise ValueError("observation binding")
        if not isinstance(hint,dict) or hint.get("source")!="phone-ocr":
            raise ValueError("authorized phone OCR required")
        w,h=hint.get("width"),hint.get("height")
        if type(w) is not int or type(h) is not int or not 0<w<=4096 or not 0<h<=4096:
            raise ValueError("OCR dimensions")
        rows=hint.get("lines")
        if not isinstance(rows,list) or len(rows)>64:
            raise ValueError("bounded OCR rows required")
        clean=[]
        for row in rows:
            if not isinstance(row,dict) or set(row)!={"text","bounds"} or not _text(row["text"]):
                raise ValueError("OCR row")
            b=row["bounds"]
            if not isinstance(b,list) or len(b)!=4 or any(type(v) is not int for v in b) or not 0<=b[0]<b[2]<=w or not 0<=b[1]<b[3]<=h:
                raise ValueError("OCR bounds")
            clean.append((_label(row["text"]),tuple(b)))
        if not isinstance(dynamic_texts,(list,tuple,set,frozenset)) or len(dynamic_texts)>64 or any(not _text(v) for v in dynamic_texts):
            raise ValueError("dynamic record fields")
        for k,v in dict(binding=binding,frame_id=frame_id,captured_at=float(captured_at),
                        width=w,height=h,lines=tuple(clean),dynamic_texts=tuple(sorted({_label(v) for v in dynamic_texts}))).items():
            object.__setattr__(self,k,v)

    @property
    def context(self):
        """Only literal static labels; an adapter explicitly supplies merchant etc."""
        dynamic=set(self.dynamic_texts)
        return tuple(sorted({t for t,_ in self.lines if t not in dynamic and not _DYNAMIC.search(t)}))

    def locate(self,target):
        found=[b for t,b in self.lines if t==_label(target)]
        return found[0] if len(found)==1 else None

    @property
    def blocked(self):
        return any(_BLOCKED_PAGE.search(t) for t,_ in self.lines)


@dataclass(frozen=True)
class Hit:
    ticket: str
    binding: Binding
    capability: str
    target: str
    bounds: tuple
    source_frame: str
    captured_at: float


class NavigationCache:
    """In-memory proposals; one outstanding hit blocks all further device hits.

    guard(binding) must check current owner/task/lease/shared-screen authorization
    and deadline. budget("ocr_navigation") must charge/check the trusted action
    budget and raise on exhaustion. A miss means return to the model, never retry
    a guessed point. Only complete() on a new matching post frame releases a hit.
    """
    def __init__(self,*,guard,budget,clock=time.monotonic,max_entries=64,max_age=2.5):
        if not callable(guard) or not callable(budget) or type(max_entries) is not int or not 1<=max_entries<=256 or type(max_age) not in (int,float) or not 0<max_age<=2.5:
            raise ValueError("guard, budget and bounded cache required")
        self.guard=guard;self.budget=budget;self.clock=clock
        self.max_entries=max_entries;self.max_age=max_age
        self._entries={};self._pending={}

    @property
    def entries(self):
        return copy.deepcopy([dict(scope=e["scope"],device=e["device"],capability=e["capability"],
                                   target=e["target"],before=e["before"],after=e["after"],
                                   successes=len(e["runs"]),promoted=e["promoted"])
                              for e in self._entries.values()])

    def _live(self,obs):
        if not isinstance(obs,Observation) or not 0<=self.clock()-obs.captured_at<=self.max_age:
            return False
        try:return self.guard(obs.binding) is True
        except Exception:return False

    def _historical_live(self,obs):
        # The dispatch observation is an immutable audited historical input.
        # Model inference can take 30s; it must not be restamped as a fresh frame.
        # The adapter attests stable_before + a bound receipt, while the current
        # independent post-frame and authority still have to be live.
        if not isinstance(obs,Observation) or not 0<=self.clock()-obs.captured_at<=600:
            return False
        try:return self.guard(obs.binding) is True
        except Exception:return False

    @staticmethod
    def _signature(obs):
        return (obs.width,obs.height,obs.context)

    @staticmethod
    def _key(scope,capability,target,before):
        return (before.binding.device,scope,capability,_label(target),NavigationCache._signature(before))

    def learn(self,*,scope,capability,target,before,after,run_id,receipt_id,
              model_ok,verified,independent,receipt_ok,stable_before):
        if not _text(scope) or capability not in _HEALTH or not _text(target) or _FORBIDDEN.search(target):
            raise ValueError("only pure text navigation may be learned")
        if not isinstance(before,Observation) or not isinstance(after,Observation):
            raise ValueError("bound OCR observations required")
        key=self._key(scope,capability,target,before)
        success=(all(v is True for v in (model_ok,verified,independent,receipt_ok,stable_before))
                 and self._historical_live(before) and self._live(after)
                 and before.binding==after.binding and before.frame_id!=after.frame_id
                 and after.captured_at>=before.captured_at
                 and not before.blocked and not after.blocked
                 and len(before.context)>=3 and len(after.context)>=3
                 and _label(target) in before.context and before.locate(target) is not None
                 and self._signature(before)!=self._signature(after)
                 and _text(run_id) and _text(receipt_id))
        if not success:
            self._entries.pop(key,None)
            return False
        expected=self._signature(after)
        entry=self._entries.get(key)
        if entry is None or entry["after"]!=expected:
            entry=dict(scope=scope,device=before.binding.device,capability=capability,
                       target=_label(target),before=self._signature(before),after=expected,
                       runs=[],receipts=[],frames=[],promoted=False)
            self._entries[key]=entry
        # A fresh run name cannot make a repeated receipt/frame independent.
        if run_id not in entry["runs"] and receipt_id not in entry["receipts"] and after.frame_id not in entry["frames"]:
            entry["runs"]=(entry["runs"]+[run_id])[-4:]
            entry["receipts"]=(entry["receipts"]+[receipt_id])[-4:]
            entry["frames"]=(entry["frames"]+[after.frame_id])[-4:]
        entry["promoted"]=len(entry["runs"])>=2
        while len(self._entries)>self.max_entries:self._entries.pop(next(iter(self._entries)))
        return entry["promoted"]

    def propose(self,scope,observation):
        if not _text(scope) or not self._live(observation) or observation.blocked or observation.binding.device in self._pending:
            return None
        signature=self._signature(observation)
        options=[(key,e) for key,e in self._entries.items()
                 if e["promoted"] and e["device"]==observation.binding.device and e["scope"]==scope and e["before"]==signature]
        # Two valid actions for the same context are ambiguous, never pick one.
        if len(options)!=1:return None
        key,entry=options[0]
        b=observation.locate(entry["target"])
        if b is None:return None
        try:self.budget("ocr_navigation")
        except Exception:return None
        if not self._live(observation):return None
        hit=Hit(uuid.uuid4().hex,observation.binding,entry["capability"],entry["target"],tuple(b),
                observation.frame_id,observation.captured_at)
        self._pending[observation.binding.device]=(hit,key,entry["after"])
        return hit

    def _take(self,hit):
        if not isinstance(hit,Hit):return None
        pending=self._pending.get(hit.binding.device)
        if pending is None or pending[0]!=hit:return None
        self._pending.pop(hit.binding.device,None)
        return pending

    def complete(self,hit,after):
        pending=self._take(hit)
        if pending is None:return False
        _,key,expected=pending
        good=(self._live(after) and after.binding==hit.binding and after.frame_id!=hit.source_frame
              and after.captured_at>=hit.captured_at and not after.blocked
              and self._signature(after)==expected)
        if not good:self._entries.pop(key,None)
        return bool(good)

    def fail(self,hit,reason="receipt_or_page_unknown"):
        """No failure can train, release a new click, or clear a write journal."""
        pending=self._take(hit)
        if pending is not None:self._entries.pop(pending[1],None)
        return False

    def export_state(self):
        """Semantic experience only. Pending hits and current coordinates stay ephemeral."""
        return dict(version=1,entries=copy.deepcopy(list(self._entries.values())))

    def restore_state(self,state):
        """Load trusted private storage defensively; it never grants live authority."""
        def signature(value):
            if not isinstance(value,(list,tuple)) or len(value)!=3:raise ValueError("signature")
            w,h,labels=value
            if type(w)is not int or type(h)is not int or not 0<w<=4096 or not 0<h<=4096 or not isinstance(labels,(list,tuple)) or not 3<=len(labels)<=64 or any(not _text(t) for t in labels):raise ValueError("signature")
            return (w,h,tuple(labels))
        try:
            if not isinstance(state,dict) or set(state)!={"version","entries"} or state["version"]!=1 or not isinstance(state["entries"],list) or len(state["entries"])>self.max_entries:raise ValueError("state")
            restored={}
            for raw in state["entries"]:
                e=copy.deepcopy(raw)
                if set(e)!={"scope","device","capability","target","before","after","runs","receipts","frames","promoted"}:raise ValueError("entry")
                if any(not _text(e[k]) for k in ("scope","device","target")) or e["capability"] not in _HEALTH or _FORBIDDEN.search(e["target"]):raise ValueError("effect")
                e["before"]=signature(e["before"]);e["after"]=signature(e["after"])
                if e["target"] not in e["before"][2] or e["before"]==e["after"]:raise ValueError("context")
                for name in ("runs","receipts","frames"):
                    a=e[name]
                    if not isinstance(a,list) or not 1<=len(a)<=4 or len(set(a))!=len(a) or any(not _text(v) for v in a):raise ValueError("provenance")
                if len({len(e[n]) for n in ("runs","receipts","frames")})!=1 or type(e["promoted"])is not bool or e["promoted"]!=(len(e["runs"])>=2):raise ValueError("promotion")
                restored[(e["device"],e["scope"],e["capability"],e["target"],e["before"])]=e
            self._entries=restored
            return True
        except (ValueError,TypeError,KeyError):return False
