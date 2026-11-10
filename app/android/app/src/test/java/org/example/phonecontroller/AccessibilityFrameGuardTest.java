package org.example.phonecontroller;
public final class AccessibilityFrameGuardTest {
 static void check(boolean v){if(!v)throw new AssertionError();}
 public static void main(String[] args){
  check(AccessibilityFrameGuard.accept(1000000000L,1100000000L,4,4,300));
  check(!AccessibilityFrameGuard.accept(1000000000L,1100000000L,4,5,300));
  check(!AccessibilityFrameGuard.accept(1000000000L,900000000L,4,4,300));
  check(!AccessibilityFrameGuard.accept(1000000000L,1500000000L,4,4,300));
  check(!AccessibilityFrameGuard.accept(1000000000L,1100000000L,4,4,149));
  System.out.println("Accessibility frame age, generation and quiet-period checks passed");
 }
}
