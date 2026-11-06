"""Existing MiMo Token Plan speech route only; no paid endpoint or fallback."""
import base64,json,os,sys,urllib.request
from pathlib import Path
from urllib.parse import urlsplit
PLAN_HOSTS=frozenset(('token-plan-cn.xiaomimimo.com','token-plan-sgp.xiaomimimo.com','token-plan-ams.xiaomimimo.com'))
def load_config():
 config=json.loads(Path(os.environ['EPAPER_SPEECH_CONFIG']).read_text())
 url=urlsplit(config.get('baseUrl',''))
 if url.scheme!='https' or url.hostname not in PLAN_HOSTS or url.username or url.password or url.query or url.path.rstrip('/')!='/v1':raise ValueError('speech subscription route required')
 if not isinstance(config.get('apiKey'),str) or not config['apiKey']:raise ValueError('speech credential unavailable')
 return config

def transcribe(path):
 config=load_config();audio=Path(path).read_bytes()
 if not 44<=len(audio)<=400000:raise ValueError('bounded WAV required')
 payload={'model':'mimo-v2.5-asr','messages':[{'role':'user','content':[{'type':'input_audio','input_audio':{'data':'data:audio/wav;base64,'+base64.b64encode(audio).decode()}}]}],'asr_options':{'language':'zh'}}
 req=urllib.request.Request(config['baseUrl'].rstrip('/')+'/chat/completions',json.dumps(payload).encode(),headers={'api-key':config['apiKey'],'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=30) as response:value=json.load(response)
 text=value['choices'][0]['message']['content'].strip()
 if not text:raise ValueError('no speech recognized')
 return {'text':text,'model':payload['model'],'provider':'xiaomi-token-plan','execution':'cloud','usage':value.get('usage')}
if __name__=='__main__':print(json.dumps(transcribe(sys.argv[1]),ensure_ascii=False))
