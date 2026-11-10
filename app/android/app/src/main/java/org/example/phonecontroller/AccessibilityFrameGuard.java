package org.example.phonecontroller;
/** Frame clocks and UI generations must agree; no wall-clock or cached nodes. */
public final class AccessibilityFrameGuard {
 private AccessibilityFrameGuard(){}
 public static boolean accept(long frameNanos,long nowNanos,long before,long after,long quietMillis){
  return frameNanos>0 && nowNanos>=frameNanos && nowNanos-frameNanos<=400000000L && before==after && quietMillis>=150;
 }
}
