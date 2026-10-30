package org.example.phonecontroller

import android.content.Context
import android.hardware.usb.*
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import io.flutter.plugin.common.MethodChannel
import org.json.JSONObject
import java.security.SecureRandom
import java.util.concurrent.Executors

/** One bounded CDC transaction at a time; retains application context, never Activity. */
class UsbProofBridge(context: Context) {
 private val manager=context.applicationContext.getSystemService(Context.USB_SERVICE) as UsbManager
 private val main=Handler(Looper.getMainLooper())
 private val worker=Executors.newSingleThreadExecutor()
 private var pending: MethodChannel.Result?=null // main thread only
 private var closed=false
 private val hex64=Regex("[0-9a-fA-F]{64}")
 private companion object { const val TIMEOUT_MS=4000L; const val MAX_BYTES=8192 }
 fun request(method: String,session: String?,nonce: String?,result: MethodChannel.Result) {
  if(closed || pending!=null){result.error("busy","USB授权正在处理中",null);return}
  if(session==null || !UsbLaunchBridge.matches(session)){result.error("usb_detached","USB连接已改变",null);return}
  if(method=="sign" && (nonce==null || !hex64.matches(nonce))){result.error("invalid_nonce","USB挑战无效",null);return}
  val serial=UsbLaunchBridge.serialFor(session)?:run {result.error("usb_detached","USB连接已改变",null);return}
  val device=UsbLaunchBridge.deviceFor(session)?:run {result.error("usb_detached","USB连接已改变",null);return}
  val generation=UsbLaunchBridge.detachGeneration
  pending=result
  worker.execute {
   var answer: Map<String,Any>?=null
   var failed=false
   try { answer=exchange(device,serial,method,nonce) {
    UsbLaunchBridge.detachGeneration==generation && UsbLaunchBridge.matches(session)
   } } catch(_: Exception){ failed=true }
   main.post {
    if(closed || pending!==result)return@post
    pending=null
    if(UsbLaunchBridge.detachGeneration!=generation || !UsbLaunchBridge.matches(session) || !live(device,serial))result.error("usb_detached","控制板已拔出，请重新插入",null)
    else if(failed || answer==null)result.error("usb_proof_failed","USB授权响应无效或超时",null)
    else result.success(answer)
   }
  }
 }
 private fun live(device: UsbDevice,serial: String): Boolean = try {
  val current=manager.deviceList[device.deviceName]
  current!=null && current.deviceId==device.deviceId && manager.hasPermission(device) &&
   current.vendorId==0x303a && current.productId in setOf(0x4001,0x4005,0x4041,0x4045) &&
   current.productName=="Epaper Phone Controller" && current.serialNumber?.uppercase()==serial
 } catch(_: Exception){false}
 private fun exchange(device: UsbDevice,serial: String,method: String,nonce: String?,sessionLive: ()->Boolean): Map<String,Any> {
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
   // Target identity and CDC interfaces were validated before bounded kernel-driver detachment.
   claimedControl=UsbInterfaceClaim.acquire { force -> connection.claimInterface(control,force) };check(claimedControl)
   claimedData=UsbInterfaceClaim.acquire { force -> connection.claimInterface(data,force) };check(claimedData)
   check(connection.controlTransfer(0x21,0x22,1,control.id,null,0,200)>=0)
   val random=ByteArray(16);SecureRandom().nextBytes(random)
   val requestId=random.joinToString(""){"%02x".format(it.toInt() and 255)}
   val command=if(method=="info")"INFO" else "AUTH ${nonce!!.lowercase()}"
   val bytes="PCUSB $requestId $command\r\n".toByteArray(Charsets.US_ASCII)
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
      val obj=JSONObject(value.substring(prefix.length).dropLast(1))
      check(obj.opt("usbSerial")==serial)
      val id=obj.getString("device");check(Regex("[A-Za-z0-9_-]{1,64}").matches(id))
      check(sessionLive() && live(device,serial))
      return if(method=="info") {
       check(obj.opt("protocol") is Number && obj.getInt("protocol")==1)
       val version=obj.getString("version");check(version.length in 1..128)
       mapOf("protocol" to 1,"device" to id,"version" to version,"usbSerial" to serial)
      } else {
       val proof=obj.getString("proof");check(hex64.matches(proof))
       mapOf("device" to id,"usbSerial" to serial,"proof" to proof.lowercase())
      }
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
 fun close() {
  closed=true;pending?.error("cancelled","USB授权已中断",null);pending=null
  worker.shutdownNow()
 }
}
