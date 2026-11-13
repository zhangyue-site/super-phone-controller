package org.example.phonecontroller;
public final class SourceBurstTest {
 static class Fake implements SourceBurst.Adapter {
  int alloc,discard,sw,closed,stopped;boolean failSwitch,failClose;long switchDelay;
  public void allocate(){alloc++;} public void discardQueued(boolean b){discard++;}
  public long switchTo(boolean b,long at){sw++;if(failSwitch)throw new IllegalStateException();return at+switchDelay;}
  public void closeSecondary(){closed++;if(failClose)throw new IllegalStateException();} public void stopCapture(){stopped++;}
 }
 static void check(boolean b){if(!b)throw new AssertionError();}
 public static void main(String[] args){
  Fake f=new Fake();SourceBurst b=new SourceBurst(f,"s",0);b.begin(0_000_000L,false);b.begin(100_000_000L,false);check(f.alloc==1);
  check(!b.image(true,0_000_000L,10_000_000L));check(b.image(true,10_000_000L,10_000_000L));check(!b.image(true,10_000_000L,11_000_000L));check(!b.image(false,11_000_000L,11_000_000L));
  b.tick(150_000_000L,"s",true,true,false,false);check(f.discard==2);check(!b.image(false,100_000_000L,160_000_000L));check(b.image(false,160_000_000L,160_000_000L));
  b.tick(3000_000_000L,"s",true,true,false,false);check(b.state()==SourceBurst.State.RESTORING);check(f.closed==0);
  check(!b.image(false,2999_000_000L,3001_000_000L));check(b.image(false,3001_000_000L,3001_000_000L));check(f.closed==1&&b.state()==SourceBurst.State.DONE);
  Fake g=new Fake();SourceBurst c=new SourceBurst(g,"s",0);c.begin(0_000_000L,false);c.tick(10_000_000L,"other",true,true,false,false);check(g.stopped==1);
  Fake h=new Fake();SourceBurst d=new SourceBurst(h,"s",0);d.begin(0_000_000L,false);d.tick(5_000_000L,"s",true,false,false,false);d.tick(1005_000_000L,"s",true,false,false,false);check(h.stopped==1&&h.closed==0);
  Fake i=new Fake();i.failSwitch=true;SourceBurst e=new SourceBurst(i,"s",0);e.begin(0_000_000L,false);check(i.stopped==1);
  Fake j=new Fake();SourceBurst k=new SourceBurst(j,"s",0);k.begin(0_000_000L,true);check(j.alloc==0);k.begin(1_000_000L,false);check(j.alloc==0);
  Fake l=new Fake();SourceBurst late=new SourceBurst(l,"s",0);late.begin(0,false);
  check(!late.image(true,3_000_000_001L,3_000_000_001L));check(late.state()==SourceBurst.State.RESTORING);
  check(!late.image(false,4_000_000_001L,4_000_000_001L));check(l.stopped==1);
  Fake m=new Fake();m.failClose=true;SourceBurst close=new SourceBurst(m,"s",0);close.begin(0,false);close.tick(5,"s",true,false,false,false);
  check(!close.image(false,6,6));check(close.state()==SourceBurst.State.FAILED);
  Fake n=new Fake();SourceBurst nano=new SourceBurst(n,"s",0);nano.begin(0,false);check(nano.image(true,1,1));check(nano.image(true,2,2));
  Fake delayed=new Fake();delayed.switchDelay=10;SourceBurst cutoff=new SourceBurst(delayed,"s",0);cutoff.begin(0,false);
  check(!cutoff.image(true,5,20));check(cutoff.image(true,11,20));
  System.out.println("PASS: replay budget, old/duplicate/wrong-reader frames, restoration confirmation, scope loss, restore timeout, switch failure, recovery exclusion");
 }
}
