package org.example.phonecontroller;
/** Pure JVM safety regression, no device or Android projection grant needed. */
public final class CaptureRecoveryGuardTest {
 static void check(boolean value){if(!value)throw new AssertionError();}
 public static void main(String[] args){
  CaptureRecoveryGuard guard=new CaptureRecoveryGuard();guard.start();long initial=guard.generation();
  check(!guard.needsAuthorization());
  check(CaptureRecoveryGuard.authorizationFailure(401));check(CaptureRecoveryGuard.authorizationFailure(403));
  for(int code:new int[]{200,202,429,500,502,503})check(!CaptureRecoveryGuard.authorizationFailure(code));
  guard.pause();check(guard.needsAuthorization());check(!guard.replace(initial+1));
  check(guard.replace(initial));check(!guard.needsAuthorization());check(!guard.replace(initial));
  long renewed=guard.generation();guard.pause();guard.stop();check(!guard.needsAuthorization());check(!guard.replace(renewed));
  guard.start();guard.pause();check(!guard.replace(renewed));check(guard.replace(guard.generation()));
  CaptureRecoveryGuard nextService=new CaptureRecoveryGuard();nextService.start();nextService.pause();
  check(!nextService.replace(guard.generation()));
  System.out.println("Capture recovery generation and HTTP classification tests passed");
 }
}
