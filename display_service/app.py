"""Private e-paper endpoint. Bind loopback behind TLS; each device has its own token."""
from collections import OrderedDict
import re
import hashlib,hmac,io,json,os,threading,time,subprocess
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
from .model import quota_rows
from .voice import validate_pcm,recognize
from .render import render
from .control import read as read_interaction, write as write_interaction

CONFIG=Path(os.environ.get('EPAPER_CONFIG','/etc/phone-controller/devices.json'))
QUOTAS=Path(os.environ.get('EPAPER_QUOTAS','/root/.local/state/quota-reporter'))
LOCK=threading.Lock()
INTERACTIONS={}
VOICE_BUSY=set()
VOICE_GENERATION={}
VOICE_CANCELLED={}


def snapshot():
    data={}
    for provider in ('codex','cursor','jev','mimo'):
        try:
            obj=json.loads((QUOTAS/(provider+'.json')).read_text())
            if isinstance(obj,dict):data[provider]=obj
        except (OSError,ValueError):pass
    return quota_rows(data,time.time())


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,code,body,kind='application/json'):
        self.send_response(code)
        self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        self.wfile.write(body)
    def device(self):
        try:devices=json.loads(CONFIG.read_text())
        except (OSError,ValueError):return None
        header=self.headers.get('Authorization','')
        for name,token in devices.items():
            if hmac.compare_digest(header,'Bearer '+token):return name
        return None
    def do_GET(self):
        self.connection.settimeout(10)
        device=self.device()
        if device is None:return self.reply(401,b'{}')
        parsed=urlparse(self.path)
        if parsed.path not in ('/screen.bin','/screen.png','/status'):return self.reply(404,b'{}')
        rows=snapshot()
        with LOCK:interaction=read_interaction(device)
        if parsed.path=='/status':
            return self.reply(200,json.dumps({'quota':rows,'interaction':interaction},ensure_ascii=False).encode())
        page=1 if parse_qs(parsed.query).get('page')==['1'] else 0
        im=render(rows,interaction,page,time.time())
        if parsed.path=='/screen.png':
            out=io.BytesIO();im.save(out,format='PNG')
            return self.reply(200,out.getvalue(),'image/png')
        return self.reply(200,im.tobytes(),'application/octet-stream')
    def do_POST(self):
        self.connection.settimeout(10)
        device=self.device()
        if device is None:return self.reply(401,b'{}')
        session=self.headers.get('X-Voice-Session','')
        seq=self.headers.get('X-Voice-Sequence','')
        valid_session=bool(re.fullmatch(r'[0-9a-f]{16}',session) and re.fullmatch(r'[0-9]{1,10}',seq))
        sequence=int(seq) if valid_session else 0
        if self.path=='/voice':
            if not valid_session or sequence<1:return self.reply(400,b'{}')
            with LOCK:
                if sequence<=VOICE_CANCELLED.get(device,{}).get(session,0):return self.reply(409,b'{}')
                if device in VOICE_BUSY:return self.reply(409,b'{}')
                VOICE_BUSY.add(device)
                generation=VOICE_GENERATION.get(device,0)
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 12800<=size<=320000:raise ValueError('invalid length')
                raw=self.rfile.read(size)
                if len(raw)!=size:raise ValueError('truncated audio')
                validate_pcm(raw)
                with LOCK:
                    if generation!=VOICE_GENERATION.get(device,0):return self.reply(409,b'{}')
                    write_interaction(device,'thinking','语音已上传，正在云端识别')
                text=recognize(raw)
                with LOCK:
                    if generation!=VOICE_GENERATION.get(device,0):return self.reply(409,b'{}')
                    write_interaction(device,'waiting',text+'（已识别；手机执行器尚未接入）')
                return self.reply(200,b'{"recognized":true,"actuatorConnected":false}')
            except (ValueError,OSError,TimeoutError,KeyError,RuntimeError,subprocess.SubprocessError):
                with LOCK:
                    if generation==VOICE_GENERATION.get(device,0):write_interaction(device,'error','语音识别失败，请靠近麦克风重试')
                return self.reply(422,b'{"recognized":false}')
            finally:
                with LOCK:VOICE_BUSY.discard(device)
        if self.path!='/stop':return self.reply(404,b'{}')
        with LOCK:
            VOICE_GENERATION[device]=VOICE_GENERATION.get(device,0)+1
            if valid_session:
                history=VOICE_CANCELLED.setdefault(device,OrderedDict())
                history[session]=max(sequence,history.get(session,0));history.move_to_end(session)
                while len(history)>16:history.popitem(last=False)
            write_interaction(device,'stopped','本机停止请求已记录；控制执行器尚未接入')
        return self.reply(200,b'{"recorded":true,"actuatorConnected":false}')


def main():
    ThreadingHTTPServer(('127.0.0.1',18943),Handler).serve_forever()

if __name__=='__main__':main()
