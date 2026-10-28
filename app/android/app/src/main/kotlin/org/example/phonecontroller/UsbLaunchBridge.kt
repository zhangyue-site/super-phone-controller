package org.example.phonecontroller

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import org.json.JSONObject

/** Identity only: never open or claim the phone's NCM/HID interfaces. */
object UsbLaunchBridge {
 private lateinit var app: Context
 private val lease=UsbSessionLease()
 private val mode=UsbModeWindow()
 private val ui=Handler(Looper.getMainLooper())
 @Volatile private var deviceName: String?=null
 @Volatile private var productId: Int?=null
 private val expiry=Runnable { if(mode.expired(SystemClock.elapsedRealtime()))revoke("控制板切换超时，屏幕共享已停止") }
 @Synchronized
 private fun checkExpiry() { if(mode.expired(SystemClock.elapsedRealtime()))revoke("控制板切换超时，屏幕共享已停止") }
 @Synchronized
 private fun revoke(message: String) {
  val oldSerial=serial;val oldSession=session
  ui.removeCallbacks(expiry);mode.clear();lease.detach()
  serial=null;session=null;deviceName=null;productId=null;error=null
  if(oldSerial!=null && ScreenShareService.usbOwnerSerial==oldSerial) {
   ScreenShareService.status=message
   app.stopService(Intent(app,ScreenShareService::class.java))
  }
  val notify=Runnable { oldSession?.let { lost?.invoke(it) };changed?.invoke(null) }
  if(Looper.myLooper()==Looper.getMainLooper())notify.run() else ui.post(notify)
 }
 /** Called immediately before an authenticated cloud-signed BLE ARM/DISARM write. */
 @Synchronized
 fun expectMode(value: String?,hid: Boolean): Boolean {
  checkExpiry()
  val current=deviceFor(value)?:return false
  if(mode.pending())return false
  val expected=if(hid)0x4045 else 0x4041
  if(current.productId==expected)return true
  if(!mode.begin(value,session,identity(current),expected,SystemClock.elapsedRealtime()))return false
  ui.postDelayed(expiry,8000)
  return true
 }
 @Volatile private var installed=false
 @Volatile private var serial: String?=null
 @Volatile private var session: String?=null
 val detachGeneration: Long get()=lease.generation()
 private var error: String?=null
 private var owner: Any?=null
 private var changed: ((Map<String,Any?>?)->Unit)?=null
 private var lost: ((String)->Unit)?=null
 private val products=setOf(0x4001,0x4005,0x4041,0x4045)
 private fun manager()=app.getSystemService(Context.USB_SERVICE) as UsbManager
 private fun identity(d: UsbDevice): String? {
  if(d.vendorId!=0x303a || d.productId !in products || d.productName!="Epaper Phone Controller") return null
  if(!manager().hasPermission(d))return null
  return try { d.serialNumber?.uppercase()?.takeIf { Regex("[0-9A-F]{12}").matches(it) } } catch(_: Exception){null}
 }
 private fun live(value: String)=manager().deviceList.values.firstOrNull { identity(it)==value && (productId==null || it.productId==productId) && (deviceName==null || it.deviceName==deviceName) }
 @Synchronized
 fun initialize(context: Context) {
  if(installed)return
  app=context.applicationContext;installed=true
  val receiver=object: BroadcastReceiver() {
   override fun onReceive(context: Context,intent: Intent) {
    onUsbEvent(intent)
   }
  }
  val filter=IntentFilter(UsbManager.ACTION_USB_DEVICE_DETACHED).apply { addAction(UsbManager.ACTION_USB_DEVICE_ATTACHED) }
  if(Build.VERSION.SDK_INT>=33)app.registerReceiver(receiver,filter,Context.RECEIVER_NOT_EXPORTED)
  else app.registerReceiver(receiver,filter)
 }
 @Synchronized
 private fun onUsbEvent(intent: Intent) {
    checkExpiry()
    val oldSession=session?:return
    @Suppress("DEPRECATION") val device=intent.getParcelableExtra<UsbDevice>(UsbManager.EXTRA_DEVICE)?:return
    if(intent.action==UsbManager.ACTION_USB_DEVICE_ATTACHED) { accept(intent);return }
    if(intent.action!=UsbManager.ACTION_USB_DEVICE_DETACHED || device.deviceName!=deviceName)return
    if(mode.detach(oldSession,SystemClock.elapsedRealtime())) {
     changed?.invoke(snapshot());return
    }
    revoke("控制板已拔出，屏幕共享已停止")
 }
 @Synchronized
 fun attachOwner(value: Any,onChanged: (Map<String,Any?>?)->Unit,onLost: (String)->Unit) {
  owner=value;changed=onChanged;lost=onLost
 }
 @Synchronized
 fun detachOwner(value: Any) { if(owner===value){owner=null;changed=null;lost=null} }
 @Synchronized
 fun accept(intent: Intent?) {
  if(intent?.action!=UsbManager.ACTION_USB_DEVICE_ATTACHED)return
  @Suppress("DEPRECATION") val requested=intent.getParcelableExtra<UsbDevice>(UsbManager.EXTRA_DEVICE)?:return
  checkExpiry()
  val actual=manager().deviceList[requested.deviceName]?:return
  if(mode.pending()) {
   val value=identity(actual)
   if(!mode.accepts(value,actual.productId,SystemClock.elapsedRealtime())) { revoke("控制板连接已改变，屏幕共享已停止");return }
   ui.removeCallbacks(expiry);mode.clear();deviceName=actual.deviceName;productId=actual.productId
   changed?.invoke(snapshot());return
  }
  if(actual.vendorId!=0x303a || actual.productId !in products || actual.productName!="Epaper Phone Controller")return
  val value=identity(actual)
  if(value==null) {error="USB设备尚未授权或无法读取序列号，请重新插入并选择本App";changed?.invoke(mapOf("error" to error));return}
  if(serial!=null && serial!=value && live(serial!!)!=null)return
  // ATTACHED may precede the delayed DETACHED broadcast. Never carry consent across it without a guard.
  if(session!=null && (serial!=value || deviceName!=actual.deviceName || productId!=actual.productId))
   revoke("控制板连接已改变，屏幕共享已停止")
  deviceName=actual.deviceName;productId=actual.productId
  adopt(value);changed?.invoke(snapshot())
 }
 @Synchronized
 private fun adopt(value: String) {
  error=null
  if(serial!=null && serial!=value) {
   // A replacement can arrive before delayed detach cleanup. Revoke old consent now.
   session?.let { lost?.invoke(it) }
   if(ScreenShareService.usbOwnerSerial==serial) {
    ScreenShareService.status="控制板已更换，屏幕共享已停止"
    app.stopService(Intent(app,ScreenShareService::class.java))
   }
  }
  if(serial!=value || session==null){serial=value;session=lease.attach(value)}
 }
 @Synchronized
 fun matches(value: String?): Boolean {
  checkExpiry()
  return installed && value!=null && value==session && lease.matches(value) &&
   (mode.permits(value,SystemClock.elapsedRealtime()) || serial?.let { live(it)!=null }==true)
 }
 @Synchronized
 fun deviceFor(value: String?): UsbDevice?=if(matches(value))serial?.let { live(it) } else null
 @Synchronized
 fun serialFor(value: String?): String?=if(matches(value))serial else null
 @Synchronized
 fun snapshot(): Map<String,Any?>? {
  if(!installed)return null
  checkExpiry()
  if(serial==null) {
   val candidates=manager().deviceList.values.filter { identity(it)!=null }
   if(candidates.size==1) {
    val actual=candidates.single();deviceName=actual.deviceName;productId=actual.productId;adopt(identity(actual)!!)
   }
  }
  error?.let{return mapOf("error" to it)}
  val value=serial?:return null
  if(live(value)==null && !mode.permits(session,SystemClock.elapsedRealtime()))return null
  val out=mutableMapOf<String,Any?>("serial" to value,"session" to session)
  val saved=app.getSharedPreferences("usb-boards",Context.MODE_PRIVATE).getString(value,null)
  try {
   if(saved!=null) {
    val data=JSONObject(saved);val remote=data.getString("remoteId");val device=data.getString("deviceId")
    if(Regex("[0-9A-F]{2}(:[0-9A-F]{2}){5}").matches(remote) && Regex("[A-Za-z0-9_-]{1,64}").matches(device)) {
     out["remoteId"]=remote;out["deviceId"]=device
    }
   }
  } catch(_: Exception) { /* Corrupt bindings require explicit first pairing again. */ }
  return out
 }
 @Synchronized
 fun forget(value: String?): Boolean {
  if(!matches(value) || ScreenShareService.active)return false
  val key=serial?:return false
  app.getSharedPreferences("usb-boards",Context.MODE_PRIVATE).edit().remove(key).apply()
  changed?.invoke(snapshot());return true
 }
 @Synchronized
 fun bind(value: String?,remote: String?,device: String?): Boolean {
  if(!matches(value) || remote==null || device==null || !Regex("[0-9A-F]{2}(:[0-9A-F]{2}){5}").matches(remote) || !Regex("[A-Za-z0-9_-]{1,64}").matches(device))return false
  val key=serial?:return false
  app.getSharedPreferences("usb-boards",Context.MODE_PRIVATE).edit().putString(key,JSONObject().put("remoteId",remote).put("deviceId",device).toString()).apply()
  return true
 }
}
