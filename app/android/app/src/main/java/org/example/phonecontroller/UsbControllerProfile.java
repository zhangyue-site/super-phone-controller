package org.example.phonecontroller;
/** USB model compatibility; cryptographic identity is still checked separately. */
public final class UsbControllerProfile {
 public static boolean fixed(int vendor,int product,String name) {
  return vendor==0x303a && product==0x4005 && "AMOLED Plugin Controller".equals(name);
 }
 public static boolean supports(int vendor,int product,String name) {
  return fixed(vendor,product,name) || (vendor==0x303a && "Epaper Phone Controller".equals(name)
   && (product==0x4001 || product==0x4005 || product==0x4041 || product==0x4045));
 }
}
