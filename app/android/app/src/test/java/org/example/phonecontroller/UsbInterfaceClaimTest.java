package org.example.phonecontroller;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
public final class UsbInterfaceClaimTest {
 private static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
 private static final class Driver implements UsbInterfaceClaim.Attempt {
  final boolean kernelBound,refuse;final List<Boolean> attempts=new ArrayList<>();
  Driver(boolean kernelBound,boolean refuse){this.kernelBound=kernelBound;this.refuse=refuse;}
  public boolean claim(boolean detach){attempts.add(detach);return !refuse&&(!kernelBound||detach);}
 }
 public static void main(String[] args){
  Driver free=new Driver(false,false);
  check(UsbInterfaceClaim.acquire(free),"unoccupied interface must work");
  check(free.attempts.equals(Arrays.asList(false)),"ordinary success must not detach a kernel driver");
  Driver kernel=new Driver(true,false);
  check(UsbInterfaceClaim.acquire(kernel),"kernel-bound CDC interface must be acquired after bounded detach");
  check(kernel.attempts.equals(Arrays.asList(false,true)),"ordinary acquisition must precede exactly one detach attempt");
  Driver refused=new Driver(true,true);
  check(!UsbInterfaceClaim.acquire(refused),"failed acquisition must remain failed");
  check(refused.attempts.equals(Arrays.asList(false,true)),"failed acquisition must not loop");
  final int[] calls={0};
  try{UsbInterfaceClaim.acquire(detach->{calls[0]++;throw new SecurityException();});throw new AssertionError("security failure must propagate");}
  catch(SecurityException expected){check(calls[0]==1,"security exceptions must not trigger detachment");}
  System.out.println("UsbInterfaceClaim resource acquisition regressions passed");
 }
}
