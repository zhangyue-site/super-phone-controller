package org.example.phonecontroller

import android.app.Activity
import android.content.Intent
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbManager
import android.os.Bundle
import android.util.Log

/**
 * USB 插入即拉起：只要识别为本家族控制板（VID/PID/产品名 + 12 位十六进制序列号），
 * 每次插入都打开主界面；不再区分首次/后续，也不再要求 USB 权限已授予——
 * 权限在主界面里授权。拉起本身不授予任何采集、USB 会话或 HID 能力。
 */
class UsbAttachActivity : Activity() {
 override fun onCreate(savedInstanceState: Bundle?) {
  super.onCreate(savedInstanceState)
  try {
   if(intent?.action != UsbManager.ACTION_USB_DEVICE_ATTACHED)return
   @Suppress("DEPRECATION") val requested=intent.getParcelableExtra<UsbDevice>(UsbManager.EXTRA_DEVICE)?:return
   val manager=getSystemService(USB_SERVICE) as UsbManager
   val actual=manager.deviceList[requested.deviceName]?:return
   if(!UsbControllerProfile.supports(actual.vendorId,actual.productId,actual.productName))return
   val serial=actual.serialNumber?.uppercase()?:return
   if(!Regex("[0-9A-F]{12}").matches(serial))return
   startActivity(Intent(this,MainActivity::class.java).setAction(UsbManager.ACTION_USB_DEVICE_ATTACHED).putExtra(UsbManager.EXTRA_DEVICE,actual).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
   Log.i("UsbAttach","Board attached; opening main screen")
  } catch(_:Exception) {Log.w("UsbAttach","Attachment ignored; open the app manually if setup is needed")}
  finally {finish()}
 }
}
