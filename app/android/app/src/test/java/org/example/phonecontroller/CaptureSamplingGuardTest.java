package org.example.phonecontroller;
public final class CaptureSamplingGuardTest {
 static void check(boolean value){if(!value)throw new AssertionError();}
 public static void main(String[] args){
  CaptureSamplingGuard g=new CaptureSamplingGuard();
  check(!g.begin(2000,false,true,true,true,false,0));
  check(!g.begin(2000,true,false,true,true,false,0));
  check(!g.begin(2000,true,true,false,true,false,0));
  check(!g.begin(2000,true,true,true,false,false,0));
  check(!g.begin(2000,true,true,true,true,true,0));
  check(!g.begin(2000,true,true,true,true,false,1500));
  check(g.begin(2000,true,true,true,true,false,0));
  check(!g.begin(4000,true,true,true,true,false,0)); // one restore pending
  g.restored();
  check(!g.begin(2500,true,true,true,true,false,0)); // <=one attempt/sec
  check(g.begin(3000,true,true,true,true,false,0));
  g.restored();check(!g.begin(4000,true,true,true,true,false,5000));
  check(g.begin(5000,true,true,true,true,false,3500));
  System.out.println("Capture sampling physical/auth/demand/freshness/rate guards: passed");
 }
}
