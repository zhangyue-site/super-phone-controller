package org.example.phonecontroller;
/** Rate limiter only; caller must check current physical objects under its lifecycle lock. */
public final class CaptureSamplingGuard {
 private long lastAttempt=-1;private boolean restoring=false;
 public synchronized boolean begin(long now,boolean enabled,boolean demand,boolean physical,boolean cloud,boolean busy,long eligibleAt){
  if(!enabled||!demand||!physical||!cloud||busy||restoring||now<0||eligibleAt>now||now-eligibleAt<1200||(lastAttempt>=0&&now-lastAttempt<1000))return false;
  lastAttempt=now;restoring=true;return true;
 }
 public synchronized void restored(){restoring=false;}
}
