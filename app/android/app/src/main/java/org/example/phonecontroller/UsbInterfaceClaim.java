package org.example.phonecontroller;
/** Bounded acquisition; callers must first validate the target and CDC interface. */
public final class UsbInterfaceClaim {
 private UsbInterfaceClaim() {}
 public interface Attempt { boolean claim(boolean detachKernelDriver); }
 public static boolean acquire(Attempt attempt) { return attempt.claim(false) || attempt.claim(true); }
}
