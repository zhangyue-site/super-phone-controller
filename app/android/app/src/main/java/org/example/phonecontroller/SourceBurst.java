package org.example.phonecontroller;
/** Isolated capture experiment. All timestamps are monotonic nanoseconds.
 * Serialize every callback on the capture handler. Adapter stopCapture owns both readers.
 * The adapter must check trusted scope/authorization before every image callback. */
public final class SourceBurst {
 public interface Adapter { void allocate(); void discardQueued(boolean secondary); long switchTo(boolean secondary,long requestedAt); void closeSecondary(); void stopCapture(); }
 public enum State { IDLE, BURST, RESTORING, DONE, FAILED }
 private final Adapter adapter; private final String scope; private final long start, deadline;
 private State state=State.IDLE; private long switchedAt,lastAccepted=-1,lastSwitch; private int switches,accepted; private boolean secondary,attempted;
 public SourceBurst(Adapter a,String scope,long now){if(a==null||scope==null||scope.isEmpty())throw new IllegalArgumentException();adapter=a;this.scope=scope;start=now;deadline=Math.addExact(now,3_000_000_000L);}
 public State state(){return state;} public int accepted(){return accepted;} public int switches(){return switches;}
 private void fail(){state=State.FAILED;adapter.stopCapture();}
 public void begin(long now,boolean recoveryActive){
  if(attempted||state!=State.IDLE)return;attempted=true;
  if(recoveryActive||now<start||now>=deadline){state=State.FAILED;return;}
  try{adapter.allocate();state=State.BURST;switchReader(true,now);}catch(RuntimeException e){fail();}
 }
 private void switchReader(boolean next,long now){
  adapter.discardQueued(next);long attachedAt=adapter.switchTo(next,now);
  if(attachedAt<now)throw new IllegalStateException("invalid switch clock");
  switchedAt=attachedAt;lastSwitch=attachedAt;secondary=next;switches++;
 }
 public void tick(long now,String currentScope,boolean authorized,boolean requestActive,boolean locked,boolean ready){
  if(state==State.DONE||state==State.FAILED||state==State.IDLE)return;
  if(now<lastSwitch||!scope.equals(currentScope)||!authorized||locked){fail();return;}
  try{
   if(state==State.RESTORING){if(now-switchedAt>=1_000_000_000L)fail();return;}
   if(ready||!requestActive||now>=deadline||switches>=20){state=State.RESTORING;switchReader(false,now);return;}
   if(now-lastSwitch>=150_000_000L)switchReader(!secondary,now);
  }catch(RuntimeException e){fail();}
 }
 /** Caller must additionally pass the existing frameGate and native tracker. */
 public boolean image(boolean fromSecondary,long timestamp,long now){
  if(state!=State.BURST&&state!=State.RESTORING)return false;
  if(now<lastSwitch){fail();return false;}
  if(state==State.BURST&&now>=deadline){
   try{state=State.RESTORING;switchReader(false,now);}catch(RuntimeException e){fail();}
   return false;
  }
  if(state==State.RESTORING&&now-switchedAt>=1_000_000_000L){fail();return false;}
  if(fromSecondary!=secondary||timestamp<=switchedAt||timestamp<=lastAccepted||timestamp>now)return false;
  lastAccepted=timestamp;accepted++;
  if(state==State.RESTORING){
   try{adapter.closeSecondary();state=State.DONE;}catch(RuntimeException e){fail();return false;}
  }
  return true;
 }
}
