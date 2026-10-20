"""Private e-paper endpoint. Bind loopback behind TLS; each device has its own token."""
import hashlib,hmac,io,json,os,threading,time
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
from .model import quota_rows
from .render import render
from .control import read as read_interaction, write as write_interaction

CONFIG=Path(os.environ.get('EPAPER_CONFIG','/etc/phone-controller/devices.example.json'))
QUOTAS=Path(os.environ.get('EPAPER_QUOTAS','/var/lib/phone-controller/private/config.json'))
LOCK=threading.Lock()
INTERACTIONS={}


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
        if self.path!='/stop':return self.reply(404,b'{}')
        with LOCK:write_interaction(device,'stopped','本机停止请求已记录；控制执行器尚未接入')
        return self.reply(200,b'{"recorded":true,"actuatorConnected":false}')


def main():
    ThreadingHTTPServer(('127.0.0.1',18943),Handler).serve_forever()

if __name__=='__main__':main()
