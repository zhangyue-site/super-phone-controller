package org.example.phonecontroller;

/** Bounded, single-use exception to USB detach revocation. Time is elapsed realtime. */
public final class UsbModeWindow {
 private String session, serial;
 private int pid;
 private long deadline;
 private boolean detached;
 public synchronized boolean begin(String requested, String current, String physicalSerial, int expectedPid, long now) {
  if (session != null || requested == null || !requested.equals(current) || physicalSerial == null ||
      (expectedPid != 0x4041 && expectedPid != 0x4045)) return false;
  session=requested;serial=physicalSerial;pid=expectedPid;deadline=now+8000;detached=false;return true;
 }
 public synchronized boolean pending() { return session != null; }
 public synchronized boolean expired(long now) { return pending() && now>=deadline; }
 public synchronized long deadline() { return deadline; }
 public synchronized boolean detach(String current, long now) {
  if (!pending() || expired(now) || !session.equals(current) || detached) return false;
  detached=true;return true;
 }
 public synchronized boolean permits(String current, long now) {
  return pending() && detached && !expired(now) && session.equals(current);
 }
 public synchronized boolean accepts(String value, int product, long now) {
  return pending() && !expired(now) && serial.equals(value) && pid==product;
 }
 public synchronized void clear() { session=null;serial=null;deadline=0;detached=false; }
}
