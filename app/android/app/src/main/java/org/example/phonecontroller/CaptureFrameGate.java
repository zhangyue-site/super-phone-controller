package org.example.phonecontroller;
/** A real barrier change fences capture; an ordinary upload response must not. */
public final class CaptureFrameGate {
 private String barrier=null;private long threshold=0;
 public synchronized long threshold(){return threshold;}
 public synchronized boolean changeBarrier(String next,long now){
  if(next.equals(barrier))return false;
  barrier=next;threshold=now;return true;
 }
 public synchronized void replaceAuthorization(long now){barrier=null;threshold=now;}
 public synchronized boolean accept(long timestamp,long now){return timestamp>threshold&&timestamp<=now&&now-timestamp<=2000000000L;}
}
