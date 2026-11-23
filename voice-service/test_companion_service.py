import importlib.util,os,tempfile,unittest
from pathlib import Path
_tmp=tempfile.TemporaryDirectory();os.environ['COMPANION_DATA']=_tmp.name
s=importlib.util.spec_from_file_location('voice',Path(__file__).with_name('companion_service.py'));v=importlib.util.module_from_spec(s);s.loader.exec_module(v)
class VoiceTests(unittest.TestCase):
 def setup_turns(self,hook=None):
  self.calls=[]
  def rpc(q):
   self.calls.append(q)
   if q['op']=='sessions':return {'sessions':[{'id':'own-chat'}]}
   if q['op']=='send':return {'job':{'id':'own-job'}}
   if q['op']=='cancel':return {'job':{'status':'cancelled'}}
   if q['op']=='job':
    if hook:hook()
    return {'job':{'status':'completed','partial_content':'你好，我在呢。','result':{'history_usage':[]}}}
   raise AssertionError(q)
  return v.Turns(asr_=lambda raw:{'text':'你好','provider':'test','model':'test','usage':None},rpc=rpc,tts_=lambda text,session:b'\x01\x00'*500)
 def test_full_path_and_same_device_binding(self):
  t=self.setup_turns();t.begin('board-a','a'*16,b'\x01\x00'*6400,start=False);turn=t.turns['board-a'];t.run('board-a',turn,b'pcm')
  p=t.status('board-a','a'*16);self.assertEqual(p['state'],'ready');self.assertEqual(p['recognizedText'],'你好');self.assertEqual(len(t.audio('board-a','a'*16)),1000)
  self.assertEqual(t.played('board-a','a'*16)['state'],'done')
  with self.assertRaises(v.VoiceError):t.status('board-b','a'*16)
  with self.assertRaises(v.VoiceError):t.begin('board-a','a'*16,b'\x01\x00'*6400,start=False)
  self.assertEqual(len([x for x in self.calls if x['op']=='send']),1)
 def test_stop_while_asr_suppresses_send(self):
  t=self.setup_turns();t.begin('board-a','b'*16,b'\x01\x00'*6400,start=False);turn=t.turns['board-a']
  def stop(raw):t.stop('board-a','b'*16);return {'text':'你好'}
  t.asr=stop;t.run('board-a',turn,b'pcm');self.assertEqual(t.status('board-a','b'*16)['state'],'stopped');self.assertEqual(self.calls,[])
 def test_late_completion_never_speaks_after_stop(self):
  holder={};t=self.setup_turns(lambda:holder['t'].stop('board-a','c'*16));holder['t']=t
  t.begin('board-a','c'*16,b'\x01\x00'*6400,start=False);t.tts=lambda *args:self.fail('TTS after STOP')
  t.run('board-a',t.turns['board-a'],b'pcm');self.assertEqual(t.status('board-a','c'*16)['state'],'stopped')
  self.assertTrue(any(x['op']=='cancel' and x['job_id']=='own-job' for x in self.calls))
 def test_size_and_overlap_bounds(self):
  t=self.setup_turns()
  for data in [b'',b'x'*12799,b'x'*320001]:
   with self.assertRaises(v.VoiceError):t.begin('board-a','d'*16,data,start=False)
  t.begin('board-a','d'*16,b'x'*12800,start=False)
  with self.assertRaises(v.VoiceError):t.begin('board-a','e'*16,b'x'*12800,start=False)
class StreamingTests(unittest.TestCase):
 def test_partial_reply_visible_before_tts(self):
  holder={};seen=[];spoken=[]
  def rpc(q):
   if q['op']=='sessions':return {'sessions':[{'id':'own-chat'}]}
   if q['op']=='send':return {'job':{'id':'own-job'}}
   if q['op']=='cancel':return {}
   if q['op']=='job':
    t=holder['t'];seen.append(t.status('board-a','f'*16)['reply'])
    n=len(seen)
    return {'job':{'status':'running' if n<3 else 'completed','partial_content':['北京','北京多云','北京现在多云，六度。'][n-1],'result':{}}}
   raise AssertionError(q)
  def speak(text,session):
   self.assertEqual(seen,['','北京','北京多云']);spoken.append(text);return b'\\x01\\x00'*500
  t=v.Turns(asr_=lambda raw:{'text':'天气怎么样'},rpc=rpc,tts_=speak);holder['t']=t
  t.begin('board-a','f'*16,b'x'*12800,start=False);t.run('board-a',t.turns['board-a'],b'pcm')
  self.assertEqual(spoken,['北京现在多云，六度。']);self.assertEqual(t.status('board-a','f'*16)['state'],'ready')
 def test_expired_audio_does_not_block_new_recording(self):
  now=[0.];t=v.Turns(clock=lambda:now[0]);t.begin('board-a','a'*16,b'x'*12800,start=False);old=t.turns['board-a'];old.update(state='ready',pcm=b'old')
  now[0]=211.;t.expire();self.assertEqual(old['state'],'stopped');self.assertEqual(old['pcm'],b'');self.assertTrue(old['stop'])
  self.assertEqual(t.begin('board-a','b'*16,b'x'*12800,start=False)['state'],'recognizing')
 def test_stream_text_is_utf8_bounded(self):
  value=v.visible_text('鱼'*159+'😀'*6+'\\x00')
  self.assertLessEqual(len(value.encode()),480);self.assertNotIn('\\x00',value)
if __name__=='__main__':unittest.main()
