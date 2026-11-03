import base64
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
from display_service import local_vision as lv, app_control, app_screen
from display_service.paired_control import Pairings
from display_service.dialogue import Mailbox, Job

class LocalVisionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.addCleanup(self.tmp.cleanup)
  self.path=Path(self.tmp.name)/"manifest.json"
  self.payload=b"fake ONNX for authorization tests"
  self.sha=hashlib.sha256(self.payload).hexdigest()
  (self.path.parent/(self.sha+".onnx")).write_bytes(self.payload)
  self.manifest=dict(format="onnx",version="test",sha256=self.sha,size=len(self.payload),file=self.sha+".onnx")
  self.path.write_text(json.dumps(self.manifest))
  self.env=patch.dict(os.environ,CONTROLLER_LOCAL_MODEL_MANIFEST=str(self.path),EPAPER_REMOTE_CONTROL="1")
  self.env.start();self.addCleanup(self.env.stop)
  self.parent=True
  def parent(token):
   if not self.parent or token!="p"*43:raise PermissionError("parent revoked")
   return "test-device"
  self.pair=Pairings(parent)
  self.ticket=self.pair.redeem(self.pair.issue("p"*43)["code"])["ticket"]
  self.identity=self.pair.owner(self.ticket)
  p=patch.object(app_control,"PAIRINGS",self.pair);p.start();self.addCleanup(p.stop)
  self.now=100.
  self.mail=Mailbox(clock=lambda:self.now)
  self.task="a"*32
  self.job=Job("test-device","b"*16,1,100.,100.)
  self.job.remote_task_id=self.task
  self.job.screen_session="s"*43
  self.job.video=b"fake jpeg"
  self.job.video_source="user-consented-app-screen"
  self.job.video_received=100.
  self.job.video_sequence=1
  self.job.video_width=640;self.job.video_height=960
  self.mail.jobs["test-device"]=self.job
  self.record=dict(owner=list(self.identity),state="running",session=self.job.session,sequence=1)
  def get(owner,ident):
   if list(owner)!=self.record["owner"] or ident!=self.task:raise ValueError("owner")
   return ident,self.record
  self.remote=NS(lock=threading.RLock(),c=NS(mailbox=self.mail),jobs={self.task:self.job},_get=get)
  self.obs=lv.Observations(self.remote)
  p=patch.dict(app_screen.AUTHORITY.tickets,{self.job.screen_session:(app_screen.AUTHORITY.clock()+100,"test-device","screen")},clear=True)
  p.start();self.addCleanup(p.stop)
 def result(self):
  f=self.obs.frame(self.ticket,self.task)
  return dict(task_id=self.task,frame_id=f["frame_id"],barrier=f["barrier"],sequence=f["sequence"],model_sha256=self.sha,boxes=[dict(x=.1,y=.1,width=.2,height=.2,score=.9)],inference_ms=4.2)
 def test_manifest_hash_and_contract(self):
  m=lv.model_manifest()
  self.assertEqual(m["inputWidth"],320);self.assertEqual(m["outputLayout"],"xywh-score")
  self.assertNotIn("file",m)
  (self.path.parent/self.manifest["file"]).write_bytes(b"x"*len(self.payload))
  with self.assertRaises(ValueError):lv.model_manifest()
 def test_manifest_traversal_url_size_and_symlink(self):
  for key,value in [("file","../other.onnx"),("url","https://example.invalid"),("size",lv.MAX_MODEL+1),("size",True)]:
   with self.subTest(key=key,value=value):
    self.path.write_text(json.dumps(dict(self.manifest,**{key:value})))
    with self.assertRaises(ValueError):lv.model_manifest()
  self.path.write_text(json.dumps(self.manifest))
  file=self.path.parent/self.manifest["file"];file.unlink();file.symlink_to(self.path)
  with self.assertRaises(ValueError):lv.model_manifest()
 def test_controller_only_and_parent_rechecked(self):
  with self.assertRaises(PermissionError):self.obs.frame("p"*43,self.task)
  result=self.result();self.parent=False
  with self.assertRaises(PermissionError):self.obs.submit(self.ticket,result)
  with self.assertRaises(PermissionError):self.obs.frame(self.ticket,self.task)
 def test_cross_task_and_other_controller(self):
  with self.assertRaises(ValueError):self.obs.frame(self.ticket,"c"*32)
  other=self.pair.redeem(self.pair.issue("p"*43)["code"])["ticket"]
  with self.assertRaises(ValueError):self.obs.frame(other,self.task)
 def test_result_hints_no_commands(self):
  result=self.result()
  self.assertTrue(self.obs.submit(self.ticket,result)["accepted"])
  hint=self.obs.hints(self.ticket,self.task,result["frame_id"],result["barrier"])
  self.assertEqual(hint["boxes"],result["boxes"]);hint["boxes"].clear()
  self.assertEqual(len(self.job.local_vision_hint["boxes"]),1)
  self.assertIsNone(self.job.command)
 def test_stale_barrier_sequence_time_and_stop(self):
  for mutation in ("barrier","sequence","age","stop","cancel","capture","parent","model"):
   with self.subTest(mutation=mutation):
    self.setUp()
    result=self.result()
    if mutation=="barrier":self.job.video_barrier="f"*32
    elif mutation=="sequence":self.job.video_sequence+=1
    elif mutation=="age":self.now+=2.001
    elif mutation=="stop":self.record["state"]="stopped"
    elif mutation=="cancel":self.job.cancelled=True
    elif mutation=="capture":app_screen.AUTHORITY.tickets.clear()
    elif mutation=="parent":self.parent=False
    elif mutation=="model":result["model_sha256"]="0"*64
    with self.assertRaises((ValueError,PermissionError)):self.obs.submit(self.ticket,result)
 def test_identical_jpeg_newly_issued_sequence_rejects_old_result(self):
  old=self.result()
  self.job.video_sequence+=1
  self.obs.frame(self.ticket,self.task)
  with self.assertRaises(ValueError):self.obs.submit(self.ticket,old)
  current=self.result()
  self.assertTrue(self.obs.submit(self.ticket,current)["accepted"])
  self.assertEqual(self.obs.planner_hints(self.job,self.job.video)["sequence"],current["sequence"])
  self.parent=False
  self.assertIsNone(self.obs.planner_hints(self.job,self.job.video))
 def test_planner_hints_rechecks_all_observation_gates(self):
  for mutation in ("frame","sequence","barrier","age","stop","cancel","capture","owner","model"):
   with self.subTest(mutation=mutation):
    self.setUp()
    result=self.result();self.obs.submit(self.ticket,result)
    self.assertIsNotNone(self.obs.planner_hints(self.job,self.job.video))
    frame=self.job.video
    if mutation=="frame":frame=b"other"
    elif mutation=="sequence":self.job.video_sequence+=1
    elif mutation=="barrier":self.job.video_barrier="f"*32
    elif mutation=="age":self.now+=2.001
    elif mutation=="stop":self.record["state"]="stopped"
    elif mutation=="cancel":self.job.cancelled=True
    elif mutation=="capture":app_screen.AUTHORITY.tickets.clear()
    elif mutation=="owner":self.pair.tickets.clear()
    elif mutation=="model":(self.path.parent/self.manifest["file"]).write_bytes(b"tamper")
    self.assertIsNone(self.obs.planner_hints(self.job,frame))
 def test_model_read_delay_expires_hint_before_return(self):
  result=self.result();self.obs.submit(self.ticket,result)
  model=lv._model()
  def slow_model():
   self.now+=3
   return model
  with patch.object(lv,"_model",slow_model):
   self.assertIsNone(self.obs.planner_hints(self.job,self.job.video))
  self.now=100.
  with patch.object(lv,"_model",slow_model):
   self.assertIsNone(self.obs.hints(self.ticket,self.task,result["frame_id"],result["barrier"]))
 def test_stop_can_acquire_task_locks_during_model_read(self):
  result=self.result();self.obs.submit(self.ticket,result)
  model=lv._model()
  stopped=threading.Event()
  workers=[]
  def slow_model():
   def stop():
    with self.remote.lock,app_screen.AUTHORITY.lock,self.mail.lock:
     self.record["state"]="stopped"
     stopped.set()
   worker=threading.Thread(target=stop);workers.append(worker);worker.start()
   self.assertTrue(stopped.wait(.5),"STOP blocked by model read")
   return model
  with patch.object(lv,"_model",slow_model):
   self.assertIsNone(self.obs.planner_hints(self.job,self.job.video))
  for worker in workers:worker.join(1)
 def test_waiting_frame(self):
  self.now+=2.001
  self.assertEqual(self.obs.frame(self.ticket,self.task)["state"],"waiting")
 def test_before_first_frame_requires_live_consent(self):
  self.job.video=b""
  self.job.screen_session=""
  self.assertEqual(self.obs.frame(self.ticket,self.task)["state"],"waiting")
  app_screen.AUTHORITY.tickets.clear()
  with self.assertRaises(PermissionError):self.obs.frame(self.ticket,self.task)
 def test_result_bounds(self):
  for value in (float("nan"),float("inf"),True,-1,1.1):
   result=self.result();result["boxes"][0]["score"]=value
   with self.assertRaises(ValueError):self.obs.submit(self.ticket,result)
  result=self.result();result["boxes"]*=101
  with self.assertRaises(ValueError):self.obs.submit(self.ticket,result)
 def test_http_binary_and_target_denial(self):
  def request(route,body,ticket=None,method="POST"):
   raw=json.dumps(body).encode()
   h=NS(path="/app-local-vision/"+route,command=method,headers={"Content-Length":str(len(raw)),"Authorization":"Bearer "+(ticket or self.ticket)},rfile=io.BytesIO(raw))
   h.reply=lambda *args:setattr(h,"response",args)
   self.assertTrue(lv.handle(h))
   return h.response
  self.assertEqual(request("model",dict(sha256=self.sha)),(200,self.payload,"application/octet-stream"))
  self.assertEqual(request("manifest",{},ticket="p"*43)[0],403)
  self.assertEqual(request("manifest",{},method="GET")[0],405)
  self.assertEqual(request("model",dict(sha256="0"*64))[0],409)
  self.assertEqual(request("manifest",dict(padding="x"*32768))[0],409)
  with patch.object(lv,"OBSERVATIONS",self.obs):
   response=request("frame",dict(task_id=self.task))
   self.assertEqual(response[0],200)
   self.assertEqual(base64.b64decode(json.loads(response[1])["jpegBase64"]),self.job.video)
   result=self.result()
   self.assertEqual(request("result",result)[0],200)
   self.record["state"]="stopped"
   self.assertEqual(request("result",result)[0],409)

if __name__=="__main__":unittest.main()
