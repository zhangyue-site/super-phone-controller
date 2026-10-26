package org.example.phonecontroller

import android.app.Activity
import android.content.Intent
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbManager
import android.os.Bundle
import android.util.Log

/** A USB attachment is a background event after first setup, never a navigation command. */
class UsbAttachActivity : Activity() {
 override fun onCreate(savedInstanceState: Bundle?) {
  super.onCreate(savedInstanceState)
  try {
   if(intent?.action != UsbManager.ACTION_USB_DEVICE_ATTACHED)return
   @Suppress("DEPRECATION") val requested=intent.getParcelableExtra<UsbDevice>(UsbManager.EXTRA_DEVICE)?:return
   val manager=getSystemService(USB_SERVICE) as UsbManager
   val actual=manager.deviceList[requested.deviceName]?:return
   if(actual.vendorId!=0x303a || actual.productId !in setOf(0x4001,0x4005,0x4041,0x4045) || actual.productName!="Epaper Phone Controller" || !manager.hasPermission(actual))return
   val serial=actual.serialNumber?.uppercase()?:return
   if(!Regex("[0-9A-F]{12}").matches(serial))return
   val prefs=getSharedPreferences("usb-auto-open",MODE_PRIVATE)
   if(prefs.getBoolean(serial,false)) {Log.i("UsbAttach","Background attachment; main screen retained in background");return}
   // This preference only suppresses UI. It never grants capture, USB sessions, or HID.
   if(!prefs.edit().putBoolean(serial,true).commit())return
   startActivity(Intent(this,MainActivity::class.java).setAction(UsbManager.ACTION_USB_DEVICE_ATTACHED).putExtra(UsbManager.EXTRA_DEVICE,actual).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
   Log.i("UsbAttach","First attachment; opened setup once")
  } catch(_:Exception) {Log.w("UsbAttach","Attachment ignored; open the app manually if setup is needed")}
  finally {finish()}
 }
}
