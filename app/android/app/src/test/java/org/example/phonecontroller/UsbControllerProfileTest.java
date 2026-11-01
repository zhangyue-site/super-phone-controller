package org.example.phonecontroller;
public class UsbControllerProfileTest {
 public static void main(String[] args) {
  assert UsbControllerProfile.supports(0x303a,0x4005,"AMOLED Plugin Controller");
  assert UsbControllerProfile.fixed(0x303a,0x4005,"AMOLED Plugin Controller");
  for(int pid:new int[]{0x4001,0x4005,0x4041,0x4045}) {
   assert UsbControllerProfile.supports(0x303a,pid,"Epaper Phone Controller");
   assert !UsbControllerProfile.fixed(0x303a,pid,"Epaper Phone Controller");
  }
  assert !UsbControllerProfile.supports(0x303a,0x4045,"AMOLED Plugin Controller");
  assert !UsbControllerProfile.supports(0x303b,0x4005,"AMOLED Plugin Controller");
  assert !UsbControllerProfile.supports(0x303a,0x4005,null);
  assert !UsbControllerProfile.supports(0x303a,0x4005,"Unknown");
  System.out.println("Legacy and fixed AMOLED USB profiles passed");
 }
}
