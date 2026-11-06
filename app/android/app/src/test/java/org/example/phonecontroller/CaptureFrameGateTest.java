package org.example.phonecontroller;
public final class CaptureFrameGateTest {
 static void check(boolean b){if(!b)throw new AssertionError();}
 public static void main(String[] args){
  CaptureFrameGate g=new CaptureFrameGate();
  check(g.changeBarrier("idle",100));check(!g.accept(100,120));check(g.accept(110,120));
  check(!g.changeBarrier("idle",200));check(g.threshold()==100);check(g.accept(150,210));
  check(g.changeBarrier("task-a",300));check(!g.accept(250,310));check(!g.accept(300,310));check(g.accept(301,310));
  check(!g.changeBarrier("task-a",400));check(g.accept(350,450));
  g.replaceAuthorization(500);check(!g.accept(499,510));check(g.changeBarrier("task-a",510));check(!g.accept(505,520));check(g.accept(511,520));
  check(!g.accept(511,2000000512L));
  System.out.println("Frame barriers preserve post-fence source timestamps without per-response starvation: passed");
 }
}
