package org.example.phonecontroller;
/** Android-independent bounds for one read-only recognition run. */
public final class RecognitionProgress {
 private final long epoch,started,afterFrame;
 private long last=0,pending=0,offeredAt=0,lastProgress;
 private int count=0;private String state="running";
 public RecognitionProgress(long epoch,long now){this(epoch,now,0);}
 public RecognitionProgress(long epoch,long now,long afterFrame){this.epoch=epoch;started=now;lastProgress=now;this.afterFrame=afterFrame;}
 public synchronized boolean offer(long frame,long age,long captureEpoch,long now){
  poll(now);
  if(!state.equals("running"))return false;
  if(captureEpoch!=epoch){state="capture_changed";return false;}
  if(pending!=0||frame<=last||frame<=afterFrame||frame<=0||age<0||age>2500)return false;
  last=frame;pending=frame;offeredAt=now;return true;
 }
 public synchronized boolean complete(long frame,long now){
  poll(now);if(!state.equals("running")||frame!=pending||pending==0)return false;
  pending=0;count++;lastProgress=now;if(count==10)state="done";return true;
 }
 public synchronized void poll(long now){
  if(!state.equals("running"))return;
  if(now-started>=90000)state="timeout";
  else if(pending!=0&&now-offeredAt>12000)state="inference_timeout";
  else if(pending==0&&now-lastProgress>12000)state="frame_timeout";
 }
 public synchronized void stop(String reason){if(state.equals("running"))state=reason;}
 public synchronized int count(){return count;}
 public synchronized String state(){return state;}
}
