package org.example.phonecontroller;
import java.util.concurrent.atomic.AtomicLong;
/** Cloud authorization is independent of a still-live system projection. */
public final class CaptureRecoveryGuard {
 private static final AtomicLong epochs=new AtomicLong();
 private long generation;
 private boolean live, required;
 public synchronized void start(){generation=epochs.incrementAndGet();live=true;required=false;}
 public synchronized void stop(){generation=epochs.incrementAndGet();live=false;required=false;}
 public synchronized void pause(){if(live)required=true;}
 public synchronized long generation(){return generation;}
 public synchronized boolean needsAuthorization(){return live&&required;}
 public synchronized boolean replace(long expected){
  if(!live||!required||expected!=generation)return false;
  generation=epochs.incrementAndGet();required=false;return true;
 }
 public static boolean authorizationFailure(int code){return code==401||code==403;}
}
