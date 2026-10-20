"""Authenticated text/task and optional cloud voice endpoints for phone agents."""
import array,contextlib,hmac,http.server,json,math,os,signal,subprocess,threading,time,uuid,wave
from pathlib import Path
from audio_upload import read_pcm
from task_request import select_task,script_for_text
ROOT=Path('/opt/cardputer-phone');LOCK=threading.Lock()
TOKEN=json.loads((ROOT/'config.json').read_text())['token']
class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version='HTTP/1.0'
    def log_message(self,*args):pass
    def do_POST(self):
        self.connection.settimeout(20)
        if self.path not in ('/voice','/task') or not hmac.compare_digest(self.headers.get('X-Phone-Token',''),TOKEN):self.send_error(403);return
        if not LOCK.acquire(blocking=False):self.send_error(409,'Task busy');return
        process=None;path=ROOT/'state/voice.wav';responded=False
        try:
            if self.path=='/task':
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4096:raise ValueError('Invalid task body')
                body=json.loads(self.rfile.read(size))
                job=select_task(body)
                arguments=['/usr/bin/python3',str(ROOT/job['script']),*job['args']]
                result_name=job['result']
                self.send_response(200);self.send_header('Content-Type','application/x-ndjson');self.end_headers();responded=True
                with (ROOT/'state'/result_name).open('w') as output, (ROOT/'state/task-error.log').open('w') as error:
                    process=subprocess.Popen(arguments,stdout=output,stderr=error,start_new_session=True)
                    began=time.monotonic()
                    while process.poll() is None:
                        if time.monotonic()-began>job['timeout']:raise TimeoutError('Task timed out')
                        self.wfile.write(b'{"stage":"AI running"}\n');self.wfile.flush();time.sleep(1)
                stage='Agent finished' if process.returncode==0 else 'Task failed'
                self.wfile.write((json.dumps({'stage':stage})+'\n').encode());self.wfile.flush()
                return
            raw=read_pcm(self.rfile,self.headers)
            if len(raw)<12800 or len(raw)%2:raise ValueError('Hold Enter and speak for at least 0.4 seconds')
            samples=array.array('h',raw)
            rms=math.sqrt(sum(s*s for s in samples)/len(samples))
            if rms<80:raise ValueError('Audio is silent; please speak closer to the board')
            self.send_response(200);self.send_header('Content-Type','application/x-ndjson');self.end_headers()
            responded=True
            def emit(stage,**kwargs):
                self.wfile.write((json.dumps(dict(stage=stage,**kwargs),ensure_ascii=False)+'\n').encode());self.wfile.flush()
            def wait(child,stage,timeout):
                start=time.monotonic()
                while child.poll() is None:
                    if time.monotonic()-start>timeout:raise TimeoutError(stage+' timeout')
                    emit(stage);time.sleep(2)
            with wave.open(str(path),'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(raw)
            with (ROOT/'state/asr-result.json').open('w') as output:
                process=subprocess.Popen(['/usr/bin/python3',str(ROOT/'asr.py'),str(path)],stdout=output,stderr=subprocess.DEVNULL,start_new_session=True)
                wait(process,'Recognizing',40)
            if process.returncode:raise RuntimeError('Cloud ASR failed')
            text=json.loads((ROOT/'state/asr-result.json').read_text())['text'].strip()
            if not text:raise ValueError('No speech recognized')
            emit('Recognized',text=text)
            (ROOT/'state/voice-task.txt').write_text(text)
            with (ROOT/'state/voice-agent-result.json').open('w') as output,(ROOT/'state/voice-agent-stderr.log').open('w') as error:
                process=subprocess.Popen(['/usr/bin/python3',str(ROOT/script_for_text(text)),'--task',text],stdout=output,stderr=error,start_new_session=True)
                wait(process,'AI running',340)
            emit('Agent finished' if process.returncode==0 else 'Task failed')
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception as e:
            (ROOT/'state/voice-server-error.json').write_text(json.dumps({'time':time.time(),'error':str(e)[:160]}))
            with contextlib.suppress(Exception):
                if not responded:self.send_response(400);self.send_header('Content-Type','application/x-ndjson');self.end_headers()
                self.wfile.write((json.dumps({'stage':'Error','error':str(e)[:120]})+'\n').encode());self.wfile.flush()
        finally:
            if process and process.poll() is None:
                with contextlib.suppress(ProcessLookupError):os.killpg(process.pid,signal.SIGTERM)
            marker=ROOT/'state/retain-next-test-audio'
            if marker.exists():
                if time.time()-marker.stat().st_mtime<90 and path.exists():
                    (ROOT/'state/hardware-test.wav').write_bytes(path.read_bytes())
                marker.unlink(missing_ok=True)
            path.unlink(missing_ok=True);LOCK.release()
if __name__=='__main__':http.server.ThreadingHTTPServer(('127.0.0.1',18894),Handler).serve_forever()
