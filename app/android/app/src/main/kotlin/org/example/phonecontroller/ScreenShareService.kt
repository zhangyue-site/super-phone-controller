package org.example.phonecontroller

import android.app.*
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.graphics.Point
import android.view.WindowManager
import org.json.JSONObject
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.*
import java.io.ByteArrayOutputStream
import java.net.URL
import javax.net.ssl.HttpsURLConnection
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit
import java.util.concurrent.RejectedExecutionException
import java.util.concurrent.RejectedExecutionHandler

class ScreenShareService: Service() {
 companion object {
 @Volatile private var current: ScreenShareService?=null
 private val renewalWorker=ThreadPoolExecutor(1,1,0L,TimeUnit.MILLISECONDS,ArrayBlockingQueue<Runnable>(1))
 fun captureSession(session: String): Map<String,Any>? = current?.captureContext(session)
 fun replaceUsbCapture(session: String,serial: String,generation: Long,capability: String,complete: (Boolean)->Unit) {
  val service=current
  val queue=service?.handler
  if(service==null || queue==null){complete(false);return}
  val posted=queue.post {
   val replaced=service.replaceCapture(session,serial,generation,capability)
   Handler(Looper.getMainLooper()).post { complete(replaced) }
  }
  if(!posted)complete(false)
 }
 fun stopRecovery() { current?.endCapture() }
 fun usbWindow(session: String, body: JSONObject, complete: (String?)->Unit) {
  val service=current
  if(service==null) { complete(null);return }
  try { renewalWorker.execute {
   var answer: String?=null
   var c: HttpsURLConnection?=null
   try {
    val capability=service.ticket
    val expectedProjection=service.projection
    check(service.renewalValid(session,capability,expectedProjection))
    c=URL(BuildConfig.CONTROLLER_BASE_URL+"/app-relay/usb-window").openConnection() as HttpsURLConnection
    c.requestMethod="POST";c.connectTimeout=1500;c.readTimeout=1500;c.doOutput=true
    c.setRequestProperty("Authorization","Bearer $capability");c.setRequestProperty("Content-Type","application/json")
    val bytes=body.toString().toByteArray(Charsets.UTF_8)
    c.setFixedLengthStreamingMode(bytes.size);c.outputStream.use { it.write(bytes) }
    check(c.responseCode==200)
    val response=c.inputStream.use { service.readBounded(it,4097) }
    check(response.size<=4096 && service.renewalValid(session,capability,expectedProjection))
    answer=String(response,Charsets.UTF_8)
   } catch(_: Exception) {} finally { c?.disconnect();Handler(Looper.getMainLooper()).post { complete(answer) } }
  } } catch(_: RejectedExecutionException) { complete(null) }
 }
 fun renewUsbCapture(proof: JSONObject, session: String, complete: (Boolean)->Unit) {
  val service=current
  if(service==null) { complete(false);return }
  try { renewalWorker.execute { service.renew("",session,complete,proof) } }
  catch(_: RejectedExecutionException) { complete(false) }
 }
 fun renewCapture(controlTicket: String, session: String, complete: (Boolean)->Unit) {
  val service=current
  if(service==null) { complete(false);return }
  try { renewalWorker.execute { service.renew(controlTicket,session,complete) } }
  catch(_: RejectedExecutionException) { complete(false) }
 }
 @Volatile var active=false
 @Volatile var usbOwnerSerial: String?=null
  @Volatile var usbOwnerSession: String?=null
 @Volatile var status="未共享"
 @Volatile var taskStatus=""
 fun revoke(capability: String) { if(capability.isEmpty())return;Thread {
  var c: HttpsURLConnection?=null
  try { c=URL("$BASE/stop").openConnection() as HttpsURLConnection;c.requestMethod="POST";c.connectTimeout=3000;c.readTimeout=3000;c.doOutput=true;c.setRequestProperty("Authorization","Bearer $capability");c.setFixedLengthStreamingMode(0);c.outputStream.close();c.responseCode } catch(_: Exception) {} finally {c?.disconnect()}
 }.start() }
 private val BASE=BuildConfig.CONTROLLER_BASE_URL + "/app-screen" }
 private fun readBounded(input: java.io.InputStream,limit: Int): ByteArray {
  val out=ByteArrayOutputStream();val buffer=ByteArray(1024)
  while(out.size()<limit){val n=input.read(buffer,0,minOf(buffer.size,limit-out.size()));if(n<0)break;out.write(buffer,0,n)}
  return out.toByteArray()
 }
 private val recovery=CaptureRecoveryGuard()
 @Volatile private var projection: MediaProjection?=null
 private var display: VirtualDisplay?=null
 private var reader: ImageReader?=null
 private var worker: HandlerThread?=null
 private var handler: Handler?=null
 private var statusWorker: HandlerThread?=null
 private var statusHandler: Handler?=null
 // One upload in flight and one newest pending frame; never accumulate old screens.
 private val frameWorker=ThreadPoolExecutor(1,1,0L,TimeUnit.MILLISECONDS,
  ArrayBlockingQueue<Runnable>(1),RejectedExecutionHandler { task, executor ->
   (executor.queue.poll() as? FrameTask)?.discard()
   if(!executor.isShutdown)executor.execute(task) else (task as? FrameTask)?.discard()
  })
 @Volatile private var statusConnection: HttpsURLConnection?=null
 @Volatile private var running=false
 @Volatile private var connection: HttpsURLConnection?=null
 @Volatile private var ticket=""
 @Volatile private var sequence=0
 private var last=0L
 @Volatile private var fastFramesUntil=0L
 @Volatile private var until=0L
 @Volatile private var renewalConnection: HttpsURLConnection?=null
 @Volatile private var barrier=""
 @Volatile private var afterResponse=0L
 private var initialWidth=0
 private var initialHeight=0
 private var initialRotation=0
 private var displayManager: DisplayManager?=null
 private var keepAwake: PowerManager.WakeLock?=null
 private var originalTimeout: Int=-1
 @Synchronized private fun projectionValid(session: String): Boolean =
  current===this && active && running && projection!=null && usbOwnerSession==session &&
  UsbLaunchBridge.matches(session) && usbOwnerSerial==UsbLaunchBridge.serialFor(session)
 @Synchronized private fun captureContext(session: String): Map<String,Any>? {
  if(!projectionValid(session))return null
  if(SystemClock.elapsedRealtime()>=until)pauseCloud(ticket)
  return mapOf("generation" to recovery.generation(),"serial" to (usbOwnerSerial?:""),"needsAuthorization" to recovery.needsAuthorization())
 }
 @Synchronized private fun replaceCapture(session: String,serial: String,generation: Long,capability: String): Boolean {
  if(!projectionValid(session) || usbOwnerSerial!=serial || !Regex("[A-Za-z0-9_-]{43}").matches(capability) || !recovery.replace(generation))return false
  ticket=capability;until=SystemClock.elapsedRealtime()+270000L
  sequence=0;barrier="";afterResponse=System.nanoTime();taskStatus=""
  status="共享已恢复，等待新任务；旧任务不会重放"
  return true
 }
 @Synchronized private fun pauseCloud(capability: String) {
  if(!running || !active || ticket!=capability)return
  SafeDiagnostics.record(mapOf("event" to "capture_pause","phase" to "capture","reason" to "cloud_auth","generation" to recovery.generation()))
  recovery.pause();taskStatus="";status="云端授权暂不可用，保留屏幕共享并自动恢复连接"
 }
 @Synchronized private fun endCapture() { recovery.stop();running=false;active=false }
 private fun renewalValid(session: String, capability: String, expectedProjection: MediaProjection?): Boolean =
  current===this && active && running && expectedProjection!=null && projection===expectedProjection &&
  ticket==capability && capability.isNotEmpty() && usbOwnerSession==session &&
  UsbLaunchBridge.matches(session) && !recovery.needsAuthorization() && SystemClock.elapsedRealtime()<until
 private fun renew(controlTicket: String,session: String,complete: (Boolean)->Unit, usbProof: JSONObject?=null) {
  var c: HttpsURLConnection?=null
  var renewed=false
  try {
   if((usbProof==null && !Regex("[A-Za-z0-9_-]{43}").matches(controlTicket)) || session.isEmpty())return
   val capability=ticket
   val expectedProjection=projection
   synchronized(this) { if(!renewalValid(session,capability,expectedProjection))return }
   c=URL(BuildConfig.CONTROLLER_BASE_URL+(if(usbProof==null) "/app-control/screen-renew" else "/app-screen/usb-renew")).openConnection() as HttpsURLConnection
   renewalConnection=c
   c.requestMethod="POST";c.connectTimeout=3000;c.readTimeout=3000;c.doOutput=true
   c.setRequestProperty("Authorization","Bearer ${if(usbProof==null) controlTicket else capability}");c.setRequestProperty("Content-Type","application/json")
   val body=(if(usbProof==null) JSONObject().put("ticket",capability) else usbProof).toString().toByteArray(Charsets.UTF_8)
   c.setFixedLengthStreamingMode(body.size);c.outputStream.use { it.write(body) }
   if(c.responseCode!=200){if(CaptureRecoveryGuard.authorizationFailure(c.responseCode))pauseCloud(capability);return}
   val bytes=c.inputStream.use { readBounded(it,4097) }
   if(bytes.size>4096)return
   val response=JSONObject(String(bytes,Charsets.UTF_8))
   if(response.optString("scope")!="screen-frames" || response.optInt("expiresIn")!=300)return
   synchronized(this) {
    if(!renewalValid(session,capability,expectedProjection))return
    until=SystemClock.elapsedRealtime()+270000L
    renewed=true
   }
  } catch(_: Exception) { /* Keep original expiry on any failed renewal. */ }
  finally { c?.disconnect();renewalConnection=null;Handler(Looper.getMainLooper()).post { complete(renewed) } }
 }
 private fun geometryChanged() {
  if(!running)return
  SafeDiagnostics.record(mapOf("event" to "capture_stop","phase" to "capture","reason" to "geometry_change","generation" to recovery.generation()))
  endCapture();connection?.disconnect();status="屏幕方向或共享范围已改变，任务已取消；请重新共享整个屏幕";taskStatus="";stopSelf()
 }
 private val displayListener=object: DisplayManager.DisplayListener {
  override fun onDisplayAdded(id: Int) {}
  override fun onDisplayRemoved(id: Int) { if(id==android.view.Display.DEFAULT_DISPLAY)geometryChanged() }
  override fun onDisplayChanged(id: Int) {
   if(id!=android.view.Display.DEFAULT_DISPLAY)return
   @Suppress("DEPRECATION") val d=(getSystemService(WINDOW_SERVICE) as WindowManager).defaultDisplay
   val size=Point();d.getRealSize(size)
   if(size.x!=initialWidth || size.y!=initialHeight || d.rotation!=initialRotation)geometryChanged()
  }
 }
 private val poll=object: Runnable {
  override fun run() {
   if(!running)return
   if(SystemClock.elapsedRealtime()>=until)pauseCloud(ticket)
   if(recovery.needsAuthorization()){statusHandler?.postDelayed(this,2000);return}
   val requestTicket=ticket
   var c: HttpsURLConnection?=null
   try {
    c=URL("$BASE/status").openConnection() as HttpsURLConnection;statusConnection=c
    c.requestMethod="POST";c.connectTimeout=3000;c.readTimeout=3000;c.doOutput=true
    c.setRequestProperty("Authorization","Bearer $requestTicket");c.setFixedLengthStreamingMode(0);c.outputStream.close()
    if(c.responseCode==200) {
     val body=c.inputStream.use { readBounded(it,16385) }
     if(body.size>16384)throw IllegalStateException()
     val data=JSONObject(String(body,Charsets.UTF_8))
     if(running && ticket==requestTicket)taskStatus=data.toString()
    } else if(CaptureRecoveryGuard.authorizationFailure(c.responseCode)) {pauseCloud(requestTicket)}
    else if(running)status="云端暂不可用，保留共享并重试"
   } catch(_: Exception) {if(running)taskStatus=""} finally {c?.disconnect();statusConnection=null}
   if(running)statusHandler?.postDelayed(this,2000)
  }
 }
 private inner class FrameTask(private val bitmap: Bitmap,private val capturedAt: Long,
  private val requestTicket: String): Runnable {
  fun discard() { bitmap.recycle() }
  override fun run() {
   var cropped: Bitmap?=null
   var scaled: Bitmap?=null
   try {
    if(!running || ticket!=requestTicket || capturedAt<=afterResponse || recovery.needsAuthorization())return
    cropped=Bitmap.createBitmap(bitmap,0,0,initialWidth,initialHeight)
    // Encode the entire screen on the upload worker, preserving normalized coordinates.
    val factor=minOf(1.0,720.0/initialWidth,1280.0/initialHeight)
    scaled=if(factor<1.0)Bitmap.createScaledBitmap(cropped!!,(initialWidth*factor).toInt().coerceAtLeast(1),(initialHeight*factor).toInt().coerceAtLeast(1),true) else cropped
    val bytes=ByteArrayOutputStream().use { out -> scaled!!.compress(Bitmap.CompressFormat.JPEG,70,out);out.toByteArray() }
    if(bytes.size>524288){endCapture();status="画面过大，请降低屏幕分辨率后重新共享";stopSelf();return}
    uploadFrame(bytes,capturedAt,requestTicket)
   } catch(_: Exception) {if(running && ticket==requestTicket)status="画面编码失败，正在重试"}
   finally {if(scaled!==cropped)scaled?.recycle();if(cropped!==bitmap)cropped?.recycle();bitmap.recycle()}
  }
 }
 private fun uploadFrame(bytes: ByteArray,capturedAt: Long,requestTicket: String) {
  val requestBarrier: String
  val requestSequence: Int
  synchronized(this) {
   if(!running || ticket!=requestTicket || recovery.needsAuthorization() ||
      capturedAt<=afterResponse || SystemClock.elapsedRealtime()>=until)return
   requestBarrier=barrier;requestSequence=++sequence
  }
  try {
     val conn=URL("$BASE/frame").openConnection() as HttpsURLConnection
     connection=conn;conn.requestMethod="POST";conn.connectTimeout=5000;conn.readTimeout=5000;conn.doOutput=true
     conn.setRequestProperty("X-Screen-Native-Width",initialWidth.toString());conn.setRequestProperty("X-Screen-Native-Height",initialHeight.toString());conn.setRequestProperty("X-Screen-Barrier",requestBarrier);conn.setRequestProperty("Authorization","Bearer $requestTicket");conn.setRequestProperty("Content-Type","image/jpeg");conn.setRequestProperty("X-Screen-Sequence",requestSequence.toString());conn.setFixedLengthStreamingMode(bytes.size)
     conn.outputStream.use{it.write(bytes)}
     val code=conn.responseCode
     if(!running || ticket!=requestTicket)return
     if(code==200 || code==202) {
      val body=conn.inputStream.use { readBounded(it,4097) }
      if(body.size>4096)throw IllegalStateException()
      val response=JSONObject(String(body,Charsets.UTF_8))
      val next=response.getString("barrier")
      if(!Regex("[0-9a-f]{32}").matches(next))throw IllegalStateException()
      synchronized(this) {
       if(!running || ticket!=requestTicket)return
       barrier=next;afterResponse=System.nanoTime()
      }
      val activeFrame=next.any { it!='0' } && (code==200 || response.optString("reason") in listOf("capture barrier required","superseded frame"))
      fastFramesUntil=if(activeFrame)SystemClock.elapsedRealtime()+2500L else 0L
      if(running)status=if(code==200)"画面传输：已上传" else "画面传输：共享中"
     } else if(CaptureRecoveryGuard.authorizationFailure(code)) {pauseCloud(requestTicket)}
     else {status="画面上传暂不可用，保留共享并重试"}
     conn.disconnect();connection=null
  } catch(_: Exception) {if(running && ticket==requestTicket)status="画面上传失败，正在重试"}
  finally {connection?.disconnect();connection=null}
 }
 override fun onBind(intent: Intent?)=null
 override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
  if(intent?.action=="STOP"){SafeDiagnostics.record(mapOf("event" to "capture_stop","phase" to "capture","reason" to "user_stop","generation" to recovery.generation()));endCapture();status="已停止共享";stopSelf();return START_NOT_STICKY}
  if(running || active){intent?.getStringExtra("ticket")?.let { revoke(it) };return START_NOT_STICKY}
  val value=intent?.getStringExtra("ticket")
  @Suppress("DEPRECATION") val grant=intent?.getParcelableExtra<Intent>("grant")
  if(value==null || grant==null){stopSelf();return START_NOT_STICKY}
  val usbSession=intent?.getStringExtra("usbSession")
  if(usbSession!=null && !UsbLaunchBridge.matches(usbSession)){revoke(value);status="控制板已拔出，请重新共享";stopSelf();return START_NOT_STICKY}
  ticket=value;usbOwnerSerial=UsbLaunchBridge.serialFor(usbSession);usbOwnerSession=usbSession;active=true
  val nm=getSystemService(NOTIFICATION_SERVICE) as NotificationManager
  if(Build.VERSION.SDK_INT>=26)nm.createNotificationChannel(NotificationChannel("screen", "AI屏幕共享", NotificationManager.IMPORTANCE_LOW))
  val stop=PendingIntent.getService(this,0,Intent(this,ScreenShareService::class.java).setAction("STOP"),PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
  val builder=if(Build.VERSION.SDK_INT>=26)Notification.Builder(this,"screen") else Notification.Builder(this)
  val notification=builder.setSmallIcon(android.R.drawable.ic_menu_view).setContentTitle("正在向你的AI共享屏幕").setContentText("手机操作由控制板HID完成；点此停止共享").setOngoing(true).setContentIntent(stop).addAction(android.R.drawable.ic_menu_close_clear_cancel,"停止",stop).build()
  try {
  if(Build.VERSION.SDK_INT>=29)startForeground(71,notification,ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION) else startForeground(71,notification)
   worker=HandlerThread("screen-capture").also{it.start()};handler=Handler(worker!!.looper)
   statusWorker=HandlerThread("screen-status").also{it.start()};statusHandler=Handler(statusWorker!!.looper)
   projection=(getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager).getMediaProjection(Activity.RESULT_OK,grant)
   projection!!.registerCallback(object: MediaProjection.Callback(){override fun onStop(){SafeDiagnostics.record(mapOf("event" to "capture_stop","phase" to "capture","reason" to "system_stop","generation" to recovery.generation()));if(running)status="系统已停止共享";endCapture();stopSelf()}
    override fun onCapturedContentResize(width: Int,height: Int){if(width!=initialWidth || height!=initialHeight)geometryChanged()}},Handler(Looper.getMainLooper()))
   val metrics=resources.displayMetrics
   @Suppress("DEPRECATION") val physical=(getSystemService(WINDOW_SERVICE) as WindowManager).defaultDisplay
   val size=Point();physical.getRealSize(size)
   val width=size.x;val height=size.y
   initialWidth=width;initialHeight=height;initialRotation=physical.rotation
   displayManager=getSystemService(DISPLAY_SERVICE) as DisplayManager
   displayManager!!.registerDisplayListener(displayListener,handler)
   reader=ImageReader.newInstance(width,height,PixelFormat.RGBA_8888,2)
   until=SystemClock.elapsedRealtime()+270000L;recovery.start();running=true;current=this;taskStatus="";statusHandler!!.post(poll);status="共享中，等待语音任务"
   reader!!.setOnImageAvailableListener({ source ->
    val image=source.acquireLatestImage() ?: return@setOnImageAvailableListener
    var bitmap: Bitmap?=null
    try {
     val now=SystemClock.elapsedRealtime()
     if(!running || image.timestamp<=afterResponse)return@setOnImageAvailableListener
     @Suppress("DEPRECATION") val currentDisplay=(getSystemService(WINDOW_SERVICE) as WindowManager).defaultDisplay
     val currentSize=Point();currentDisplay.getRealSize(currentSize)
     if(currentDisplay.rotation!=initialRotation || currentSize.x!=initialWidth || currentSize.y!=initialHeight){geometryChanged();return@setOnImageAvailableListener}
     if(image.width!=initialWidth || image.height!=initialHeight){geometryChanged();return@setOnImageAvailableListener}
     if(now>=until)pauseCloud(ticket)
     if(recovery.needsAuthorization())return@setOnImageAvailableListener
     val requestTicket=ticket
     if(now-last<(if(now<fastFramesUntil)100L else 800L))return@setOnImageAvailableListener
     last=now
     val plane=image.planes[0];val padding=plane.rowStride-plane.pixelStride*image.width
     bitmap=Bitmap.createBitmap(image.width+padding/plane.pixelStride,image.height,Bitmap.Config.ARGB_8888)
     bitmap!!.copyPixelsFromBuffer(plane.buffer)
     frameWorker.execute(FrameTask(bitmap!!,image.timestamp,requestTicket))
     bitmap=null // Ownership moved to the bounded uploader; rejected frames are recycled.

    } catch(e: Exception) {if(running)status="画面上传失败，正在重试"}
    finally {bitmap?.recycle();image.close()}
   },handler)
   display=projection!!.createVirtualDisplay("AI phone screen",width,height,metrics.densityDpi,DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,reader!!.surface,null,handler)
  } catch(e: Exception) {status="屏幕共享启动失败，请重新授权";stopSelf()}
  return START_NOT_STICKY
 }
 override fun onTaskRemoved(rootIntent: Intent?) {
  // USB attach uses a temporary task; losing that task is not consent revocation.
  SafeDiagnostics.record(mapOf("event" to "capture_task_removed","phase" to "capture","reason" to "task_removed","generation" to recovery.generation(),"active" to active,"running" to running))
  super.onTaskRemoved(rootIntent)
 }
 override fun onDestroy() {
  SafeDiagnostics.record(mapOf("event" to "capture_destroy","phase" to "capture","reason" to "destroy","generation" to recovery.generation(),"active" to active,"running" to running))
  endCapture()
  synchronized(this) {
   if(current===this)current=null
   active=false;usbOwnerSerial=null;usbOwnerSession=null
   running=false
  }
  renewalConnection?.disconnect();connection?.disconnect();statusConnection?.disconnect();frameWorker.shutdownNow().forEach { (it as? FrameTask)?.discard() }
  display?.release();display=null;reader?.close();reader=null
  val old=projection;projection=null;old?.stop();worker?.quitSafely();worker=null
  handler?.removeCallbacksAndMessages(null);statusHandler?.removeCallbacksAndMessages(null);statusWorker?.quitSafely();statusWorker=null;statusHandler=null;displayManager?.unregisterDisplayListener(displayListener)
  taskStatus=""
  keepAwake?.let{if(it.isHeld)it.release()};keepAwake=null
  if(originalTimeout>=0){try{Settings.System.putInt(contentResolver,Settings.System.SCREEN_OFF_TIMEOUT,originalTimeout)}catch(_: Exception){};originalTimeout=-1}
  val capability=ticket;ticket="";revoke(capability)
  stopForeground(STOP_FOREGROUND_REMOVE);super.onDestroy()
 }
}
