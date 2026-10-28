package org.example.phonecontroller;

/** Standalone JVM safety regression: run with java -ea. */
public final class UsbModeWindowTest {
 private static void check(boolean value) { if(!value) throw new AssertionError(); }
 public static void main(String[] args) {
  UsbModeWindow w=new UsbModeWindow();
  check(!w.detach("s",0)); // Real detach never receives grace.
  check(!w.begin("wrong","s","ABC",0x4045,0));
  check(!w.begin("s","s","ABC",0x4005,0));
  check(w.begin("s","s","ABC",0x4045,100));
  check(!w.permits("s",100));
  check(!w.begin("s","s","ABC",0x4041,7000));
  check(w.deadline()==8100);
  check(w.detach("s",101));check(w.permits("s",8099));
  check(!w.detach("s",102));check(!w.permits("other",102));
  check(!w.accepts("DEF",0x4045,200));check(!w.accepts("ABC",0x4041,200));
  check(w.accepts("ABC",0x4045,8099));
  check(w.expired(8100));check(!w.permits("s",8100));check(!w.accepts("ABC",0x4045,8100));
  check(!w.begin("s","s","ABC",0x4045,9000)); // Cannot reset even expired state without revocation.
  w.clear();check(!w.pending());check(!w.permits("s",9000));
  UsbSessionLease lease=new UsbSessionLease();String old=lease.attach("ABC");
  check(w.begin(old,old,"ABC",0x4041,9000));check(w.detach(old,9001));
  check(w.accepts("ABC",0x4041,9002));w.clear();check(lease.matches(old));
  lease.detach();check(!lease.matches(old));check(!lease.attach("ABC").equals(old));
  System.out.println("UsbModeWindow safety tests passed");
 }
}
