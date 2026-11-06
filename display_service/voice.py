"""Bounded in-memory PCM input; temporary WAV removed after cloud recognition."""
import array,json,math,os,subprocess,tempfile,wave

def validate_pcm(raw):
    if not 12800<=len(raw)<=320000 or len(raw)%2:
        raise ValueError('请录音0.4至10秒')
    samples=array.array('h',raw)
    if math.sqrt(sum(x*x for x in samples)/len(samples))<80:
        raise ValueError('声音太小，请靠近麦克风')
    return raw

def asr_script():
    value=os.environ.get('EPAPER_ASR','').strip()
    if not value:raise RuntimeError('EPAPER_ASR must point to a configured speech adapter')
    return value

def recognize(raw):
    validate_pcm(raw)
    fd,path=tempfile.mkstemp(suffix='.wav')
    try:
        with os.fdopen(fd,'wb') as stream:
            with wave.open(stream,'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(raw)
        result=subprocess.run(['/usr/bin/python3',asr_script(),path],
                              capture_output=True,timeout=75,check=True)
        answer=json.loads(result.stdout)
        print('ASR_USAGE '+json.dumps({k:answer.get(k) for k in ('provider','model','usage')},ensure_ascii=False),flush=True)
        text=answer['text'].strip()[:120]
        if not text:raise ValueError('没有识别到语音')
        return text
    finally:
        os.unlink(path)
