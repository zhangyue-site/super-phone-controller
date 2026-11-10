package org.example.phonecontroller

import android.content.Context
import android.hardware.usb.*
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import io.flutter.plugin.common.MethodChannel
import java.security.SecureRandom
import java.util.concurrent.Executors

/** Local auto-loop tap executor. Reuses the bounded CDC console exchange pattern
 * of UsbProofBridge: send "PCUSB <id> TAP <x> <y>\r\n" and expect a reply line
 * "PCUSB <id> {...}". If the firmware does not recognise the command, we report
 * the timeout honestly instead of claiming a click happened. */
class LocalLoopBridge(context: Context) {
 private val manager=context.applicationContext.getSystemService(Context.USB_SERVICE) as UsbManager
 private val main=Handler(Looper.getMainLooper())
 private val worker=Executors.newSingleThreadExecutor()
 private var closed=false
 private companion object { const val TIMEOUT_MS=4000L; const val MAX_BYTES=8192 }

 fun tap(session: String?, x: Int, y: Int, result: MethodChannel.Result) {
  if(closed){result.error("busy","本地点击正在处理中",null);return}
  if(!UsbLaunchBridge.matches(session)){result.error("usb_detached","控制板已拔出，请重新插入",null);return}
  val serial=UsbLaunchBridge.serialFor(session)?:run {result.error("usb_detached","USB连接已改变",null);return}
  val device=UsbLaunchBridge.deviceFor(session)?:run {result.error("usb_detached","USB连接已改变",null);return}
  if(x<0||y<0){result.error("invalid_target","点击坐标无效",null);return}
  val generation=UsbLaunchBridge.detachGeneration
  worker.execute {
   var answer: String?=null
   var failed=false
   try { answer=exchange(device,serial,x,y) {
    UsbLaunchBridge.detachGeneration==generation && UsbLaunchBridge.matches(session)
   } } catch(_: Exception){ failed=true }
   main.post {
    if(closed)return@post
    if(UsbLaunchBridge.detachGeneration!=generation || !UsbLaunchBridge.matches(session))result.error("usb_detached","控制板已拔出，请重新插入",null)
    else if(failed || answer==null)result.error("local_tap_failed","控制板未确认本地点击（可能固件暂不支持 TAP 指令）",null)
    else result.success(mapOf("ok" to true,"reply" to answer))
   }
  }
 }

 fun close() {
  closed=true;worker.shutdownNow()
 }

 private fun live(device: UsbDevice,serial: String): Boolean = try {
  val current=manager.deviceList[device.deviceName]
  current!=null && current.deviceId==device.deviceId && manager.hasPermission(device) &&
   UsbControllerProfile.supports(current.vendorId,current.productId,current.productName) && current.serialNumber?.uppercase()==serial
 } catch(_: Exception){false}

 private fun exchange(device: UsbDevice,serial: String,x: Int,y: Int,sessionLive: ()->Boolean): String {
  check(sessionLive() && live(device,serial))
  check(device.interfaceCount>=2)
  val control=device.getInterface(0);val data=device.getInterface(1)
  check(control.id==0 && control.interfaceClass==UsbConstants.USB_CLASS_COMM)
  check(data.id==1 && data.interfaceClass==UsbConstants.USB_CLASS_CDC_DATA)
  val endpoints=(0 until data.endpointCount).map {data.getEndpoint(it)}.filter {it.type==UsbConstants.USB_ENDPOINT_XFER_BULK}
  val input=endpoints.single {it.direction==UsbConstants.USB_DIR_IN}
  val output=endpoints.single {it.direction==UsbConstants.USB_DIR_OUT}
  val connection=manager.openDevice(device)?:error("open")
  var claimedControl=false;var claimedData=false
  try {
   claimedControl=UsbInterfaceClaim.acquire { force -> connection.claimInterface(control,force) };check(claimedControl)
   claimedData=UsbInterfaceClaim.acquire { force -> connection.claimInterface(data,force) };check(claimedData)
   check(connection.controlTransfer(0x21,0x22,1,control.id,null,0,200)>=0)
   val random=ByteArray(16);SecureRandom().nextBytes(random)
   val requestId=random.joinToString(""){"%02x".format(it.toInt() and 255)}
   val bytes="PCUSB $requestId TAP $x $y\r\n".toByteArray(Charsets.US_ASCII)
   check(sessionLive() && live(device,serial))
   check(connection.bulkTransfer(output,bytes,bytes.size,200)==bytes.size)
   val deadline=SystemClock.elapsedRealtime()+TIMEOUT_MS
   val prefix="PCUSB $requestId "
   val line=StringBuilder();val chunk=ByteArray(256);var total=0
   while(SystemClock.elapsedRealtime()<deadline) {
    check(!Thread.currentThread().isInterrupted && sessionLive() && live(device,serial))
    val count=connection.bulkTransfer(input,chunk,chunk.size,200)
    if(count<=0)continue
    total+=count;check(total<=MAX_BYTES)
    for(i in 0 until count) {
     val ch=(chunk[i].toInt() and 255).toChar()
     if(ch=='\n') {
      val value=line.toString();line.setLength(0)
      if(!value.endsWith("\r") || !value.startsWith(prefix))continue
      check(sessionLive() && live(device,serial))
      return value.substring(prefix.length).dropLast(1)
     } else { check(ch=='\r' || ch.code in 32..126);line.append(ch);check(line.length<=2048) }
    }
   }
   error("timeout")
  } finally {
   if(claimedData)try {connection.releaseInterface(data)}catch(_: Exception){}
   if(claimedControl) {
    try {connection.controlTransfer(0x21,0x22,0,control.id,null,0,200)}catch(_: Exception){}
    try {connection.releaseInterface(control)}catch(_: Exception){}
   }
   connection.close()
  }
 }
}
