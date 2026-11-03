"""Private alias -> existing safe navigation plans. No script/workflow engine.

Imported plugin descriptions are untrusted metadata. Only the private registry
can select an existing RemoteControl text runner; unknown aliases fail closed.
"""
import hashlib,json,os,re,secrets,threading,time
from pathlib import Path
from string import Formatter
from . import remote_http
HEX=re.compile(r"[0-9a-f]{32}\Z")
ALIAS=re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")

def render_entry(path,entry,parameters):
    if not path:raise ValueError("插件工作流未配置，请联系维护者配置私有允许清单。")
    if not isinstance(entry,str) or not ALIAS.fullmatch(entry):raise ValueError("插件入口无效")
    if not isinstance(parameters,dict):raise ValueError("插件参数无效")
    path=Path(path)
    if path.stat().st_size>65536:raise ValueError("私有工作流清单过大")
    registry=json.loads(path.read_text())
    if not isinstance(registry,dict):raise ValueError("私有工作流清单无效")
    item=registry.get(entry)
    if not isinstance(item,dict) or set(item)!={"text","parameters"}:raise ValueError("插件工作流未配置或入口不在允许清单")
    schema=item["parameters"];template=item["text"]
    if not isinstance(schema,dict) or len(schema)>8 or not isinstance(template,str) or len(template)>120 or set(parameters)!=set(schema):raise ValueError("插件参数与私有工作流不匹配")
    values={}
    for key,rule in schema.items():
        if not isinstance(key,str) or not re.fullmatch("[a-z][a-z0-9_]{0,31}",key) or not isinstance(rule,dict):raise ValueError("工作流参数规则无效")
        if set(rule)!={"type","maxLength"} or rule["type"]!="text" or type(rule["maxLength"]) is not int or not 1<=rule["maxLength"]<=64:raise ValueError("工作流参数规则无效")
        value=parameters[key]
        if not isinstance(value,str) or not 1<=len(value)<=rule["maxLength"] or not re.fullmatch(r"[\u3400-\u9fffA-Za-z0-9 ]+",value):raise ValueError("插件参数内容无效")
        values[key]=value
    for _,field,spec,conversion in Formatter().parse(template):
        if field is not None and (field not in schema or spec or conversion):raise ValueError("工作流模板无效")
    text=template.format(**values)
    if not 1<=len(text)<=120:raise ValueError("插件计划过长")
    fingerprint=hashlib.sha256(json.dumps(item,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return text,fingerprint

class PluginSessions:
    def __init__(self,clock=time.monotonic):
        self.clock=clock;self.lock=threading.RLock();self.devices={}
    def _identity(self,device,boot,session):
        principal=hashlib.sha256((boot+session).encode()).hexdigest()
        return ("board-plugin",principal,principal,device)
    def allowed(self,identity):
        state=self.devices.get(identity[3])
        return bool(state and tuple(state["owner"])==tuple(identity) and not state["stopped"] and self.clock()<state["until"])
    def dispatch(self,device,obj,remote,path):
        if not isinstance(obj,dict):raise ValueError("插件请求无效")
        operation=obj.get("operation")
        fields={"prepare":{"entry","parameters"},"confirm":{"task_id","confirmation"},"status":{"task_id"},"stop":set()}
        common={"operation","boot","session","request_id"}
        if operation not in fields or set(obj)!=common|fields[operation]:raise ValueError("插件请求字段无效")
        for key in ("boot","session","request_id"):
            if not isinstance(obj[key],str) or not HEX.fullmatch(obj[key]):raise ValueError("插件会话无效")
        with self.lock:
            now=self.clock();state=self.devices.get(device)
            binding=(obj["boot"],obj["session"])
            if state is None:
                if operation!="prepare":raise PermissionError("插件会话未建立")
                if len(self.devices)>=256:raise ValueError("插件会话容量已满")
                state={"binding":None,"retired":set(),"requests":set(),"owner":None,"stopped":True,"until":0}
                self.devices[device]=state
            if binding in state["retired"]:raise PermissionError("插件会话已失效")
            if binding!=state["binding"]:
                if operation!="prepare":raise PermissionError("插件会话不匹配")
                if len(state["retired"])>=1024:raise PermissionError("插件会话容量已满")
                old=state["binding"]
                if old:
                    if state["owner"] and state.get("task_id"):
                        previous=remote.status(state["owner"],state["task_id"])
                        if previous["state"] in ("queued","running"):raise ValueError("控制板正在执行插件，请先明确停止")
                        if previous["state"]=="pending":
                            with remote.lock:
                                remote.records[state["task_id"]].update(state="replaced",reply="已有新的插件预览，旧确认已失效",verified=False)
                                remote._save()
                    state["retired"].add(old)
                state.update(binding=binding,requests=set(),owner=self._identity(device,*binding),stopped=False,until=now+120,task_id=None)
            elif operation=="prepare":raise PermissionError("本次手势已消费，请重新预览")
            if state["stopped"]:raise PermissionError("插件会话已停止")
            ident=obj["request_id"]
            if ident in state["requests"] or (len(state["requests"])>=512 and operation!="stop"):raise PermissionError("本次请求已消费")
            state["requests"].add(ident) # Consume before task creation or confirmation.
            owner=state["owner"]
            if operation=="prepare":
                text,fingerprint=render_entry(path,obj["entry"],obj["parameters"])
                result=remote.prepare(owner,text)
                state.update(task_id=result["task_id"],entry=obj["entry"],parameters=dict(obj["parameters"]),fingerprint=fingerprint,confirmation=secrets.token_hex(16),confirmation_until=now+120,confirmed=False)
                return result|{"confirmation":state["confirmation"]}
            if operation=="stop":
                with remote.lock:
                    record=remote.records.get(state.get("task_id"))
                    if record and record.get("owner")==list(owner):
                        if record["state"] in ("queued","running"):
                            result=remote.stop(owner)
                        else:
                            if record["state"]=="pending":
                                record.update(state="stopped",reply="本次插件计划已停止",verified=False)
                                remote._save()
                            result=dict(state="stopped",terminal=True,verified=False,reply="本次插件计划已停止")
                    else:
                        result=dict(state="stopped",terminal=True,verified=False,reply="本次插件计划已停止")
                state.update(stopped=True,until=0,confirmation=None)
                return result
            if state["stopped"] or now>=state["until"] or obj.get("task_id")!=state.get("task_id"):raise PermissionError("插件计划已失效")
            if operation=="confirm":
                if state.get("confirmed") or now>=state["confirmation_until"] or not secrets.compare_digest(str(obj["confirmation"]),str(state["confirmation"])):raise PermissionError("本次确认已失效")
                _,fingerprint=render_entry(path,state["entry"],state["parameters"])
                if fingerprint!=state["fingerprint"]:raise PermissionError("私有工作流已变化，请重新预览")
                state.update(confirmation=None,confirmed=True,until=now+250)
                return remote.confirm(owner,state["task_id"])
            return remote.status(owner,state["task_id"])

SESSIONS=PluginSessions()

def handle(handler,config=None):
    if handler.path!="/board-plugin":return False
    try:
        if handler.command!="POST":handler.reply(405,b"{}");return True
        if os.environ.get("EPAPER_REMOTE_CONTROL")!="1":handler.reply(503,b"{}");return True
        device=handler.device()
        if device is None:raise PermissionError("设备授权已失效")
        result=SESSIONS.dispatch(device,remote_http.body(handler,2048),remote_http.REMOTE,os.environ.get("CONTROLLER_PLUGIN_WORKFLOWS"))
        handler.reply(200,json.dumps(result,ensure_ascii=False).encode())
    except PermissionError as error:handler.reply(403,json.dumps({"state":"rejected","reply":str(error)},ensure_ascii=False).encode())
    except (ValueError,TypeError,KeyError,OSError) as error:
        message=str(error) if isinstance(error,ValueError) else "插件私有工作流不可用，请联系维护者"
        handler.reply(409,json.dumps({"state":"rejected","reply":message},ensure_ascii=False).encode())
    return True
