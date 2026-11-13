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
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit
import java.util.concurrent.RejectedExecutionException
import java.util.concurrent.RejectedExecutionHandler

class ScreenShareService: Service() {
 companion object {
 @Volatile private var current: ScreenShareService?=null
 fun beginRecognition(kind: String, autoEpoch: Long? = null): Pair<String,Long>? =
  current?.beginLocalRecognition(kind,autoEpoch)
 fun autoRecognitionStatus(): Map<String,Any> = current?.autoStatus() ?: emptyMap()
 fun recognitionLive(id: String): Boolean=current?.localRecognitionLive(id)?:false
 fun endRecognition(id: String){current?.endLocalRecognition(id)}

 fun recordDiagnosticSnapshot(){
  val service=current
  if(service!=null)service.recordSnapshot() else SafeDiagnostics.record(mapOf("event" to "capture_frame_stats","phase" to "frame","active" to active,"running" to false))
 }
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
 @Volatile var latestLoopFrame: LoopFrame?=null
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
 private val sampling=CaptureSamplingGuard()
 private val frameGate=CaptureFrameGate()
 private var retiredReader: ImageReader?=null
 private var swapStartedNanos=0L
 private var swapDeadline=0L
 private val sourceCallbacks=AtomicLong();private val deferredCallbacks=AtomicLong();private val statusErrors=AtomicLong()
 @Volatile private var lastCallbackAt=0L
 @Volatile private var statusOkAt=0L
 @Volatile private var statusHttp=-1
 @Volatile private var captureState="unknown"
 @Volatile private var hasStatusBarrier=false
 private val drain=Runnable { drainSource() }
 // Handler-confined transport experiment. Never changes native observation thresholds.
 private var sourceBurst: SourceBurst?=null
 private var burstPrimary: ImageReader?=null
 private var burstSecondary: ImageReader?=null
 private var burstScope=""
 private var burstKey=""
 private val attemptedBursts=linkedSetOf<String>()
 private fun burstInFlight()=sourceBurst?.state() in setOf(SourceBurst.State.BURST,SourceBurst.State.RESTORING)
 private fun burstAuthorized()=recognitionAvailable() && !recovery.needsAuthorization()
 private fun burstDiagnostic(event: String) {
  SafeDiagnostics.record(mapOf("event" to "source_burst","phase" to "frame","reason" to event,
   "switches" to (sourceBurst?.switches() ?: 0),"acquired_candidates" to (sourceBurst?.accepted() ?: 0),
   "source_frames" to sourceFrames.get(),"eligible_frames" to eligibleFrames.get()))
 }
 private val burstTick=object: Runnable {
  override fun run() { synchronized(this@ScreenShareService) {
   if(!BuildConfig.SOURCE_BURST_EXPERIMENT || !running)return
   val scope=observationScope()
   val key=if(supportsLocalObservation && hasDemand(SystemClock.elapsedRealtime()))localObservation.burstRequestKey(scope) else null
   if(sourceBurst==null && key!=null && key !in attemptedBursts && burstAuthorized() && retiredReader==null) {
    // Bound replay memory per capture: saturation disables additional attempts.
    if(attemptedBursts.size>=128)return
    attemptedBursts.add(key);burstScope=scope;burstKey=key;burstPrimary=reader
    val adapter=object: SourceBurst.Adapter {
     override fun allocate(){check(retiredReader==null && burstAuthorized());burstSecondary=newReader()}
     override fun discardQueued(secondary: Boolean) {
      val target=(if(secondary)burstSecondary else burstPrimary) ?: error("missing source")
      repeat(2){target.acquireLatestImage()?.close()}
     }
     override fun switchTo(secondary: Boolean,requestedAt: Long): Long {
      check(burstAuthorized() && observationScope()==burstScope)
      val target=(if(secondary)burstSecondary else burstPrimary) ?: error("missing source")
      handler?.removeCallbacks(drain)
      display!!.surface=target.surface;reader=target
      return System.nanoTime()
     }
     override fun closeSecondary(){
      check(reader===burstPrimary)
      burstSecondary?.setOnImageAvailableListener(null,null);burstSecondary?.close();burstSecondary=null
      burstDiagnostic("restored")
     }
     override fun stopCapture(){burstDiagnostic("failed");surfaceFailed()}
    }
    sourceBurst=SourceBurst(adapter,scope,System.nanoTime())
    sourceBurst!!.begin(System.nanoTime(),false);burstDiagnostic("begin")
   }
   val burst=sourceBurst ?: return
   if(burstInFlight())burst.tick(System.nanoTime(),scope,burstAuthorized(),key==burstKey,locked(),localObservation.burstReady(scope,lastEligibleTimestamp))
   if(burstInFlight())handler?.postDelayed(this,50L)
   else if(burst.state()==SourceBurst.State.DONE){sourceBurst=null;burstPrimary=null}
  } }
 }
 private fun closeBurstReaders(){
  handler?.removeCallbacks(burstTick)
  // Called after VirtualDisplay release; no surface can still be attached.
  val activeReader=reader
  listOfNotNull(burstPrimary,burstSecondary).distinct().filter{it!==activeReader}.forEach{
   try{it.setOnImageAvailableListener(null,null);it.close()}catch(_: Exception){}
  }
  burstPrimary=null;burstSecondary=null;sourceBurst=null;attemptedBursts.clear()
 }
 private fun newReader(): ImageReader {
  val r=ImageReader.newInstance(initialWidth,initialHeight,PixelFormat.RGBA_8888,2)
  try {r.setOnImageAvailableListener({ source -> scheduleDrain(source) },handler);return r}
  catch(error: Exception){r.close();throw error}
 }
 private fun scheduleDrain(source: ImageReader) {
  synchronized(this) {
   if(!running || source!==reader)return
   val now=SystemClock.elapsedRealtime();sourceCallbacks.incrementAndGet();lastCallbackAt=now
   val localFast=supportsLocalObservation && frameDemand && localObservation.wantsFastSamples(observationScope())
   val wait=(last+(if(now<fastFramesUntil || localFast)100L else 800L)-now).coerceIn(0L,800L)
   if(wait>0)deferredCallbacks.incrementAndGet()
   // Leave the latest real Image queued until the absolute throttle deadline.
   // New callbacks cannot postpone that deadline or discard the final image.
   handler?.removeCallbacks(drain);handler?.postDelayed(drain,wait)
  }
 }
 private fun interactive()=(getSystemService(POWER_SERVICE) as PowerManager).isInteractive
 private fun locked()=(getSystemService(KEYGUARD_SERVICE) as KeyguardManager).isKeyguardLocked
 private fun captureStateHeadersReader(): CaptureStateHeaders.Reader {
  val service=this
  return object: CaptureStateHeaders.Reader {
   override fun interactive()=service.interactive()
   override fun keyguardLocked()=service.locked()
  }
 }
 private fun recordSnapshot(){val now=SystemClock.elapsedRealtime();frameStats(now,CaptureSamplingSettings.enabled(this),hasDemand(now),true)}
 private var captureGeneration=System.nanoTime()
 private val sourceFrames=AtomicLong();private val eligibleFrames=AtomicLong();private val oldFrames=AtomicLong()
 private val uploadOk=AtomicLong();private val uploadWait=AtomicLong();private val uploadError=AtomicLong()
 private val refreshBegin=AtomicLong();private val refreshOk=AtomicLong();private val refreshCancel=AtomicLong();private val refreshError=AtomicLong()
 @Volatile private var lastSourceAt=0L
 @Volatile private var lastEligibleAt=0L
 private var lastEligibleTimestamp=0L
 @Volatile private var uploadMs=-1L
 @Volatile private var frameDemand=false
 @Volatile private var demandAt=0L
 private var statsAt=0L
 private var localRecognitionId=""
 private var localRecognitionEpoch=-1L
 private var localRecognitionUntil=0L
 private var autoStep="ocr"
 private var autoRun=""
 private fun recognitionAvailable()=running && active && interactive() && !locked() &&
  !recovery.needsAuthorization() && SystemClock.elapsedRealtime()<until &&
  projection!=null && display!=null && reader!=null &&
  usbOwnerSession?.let{projectionValid(it)}!=false
 @Synchronized private fun autoStatus(): Map<String,Any> {
  if(!recognitionAvailable() || latestLoopFrame?.captureEpoch!=captureGeneration ||
     localRecognitionId.isNotEmpty())return emptyMap()
  return mapOf("autoEpoch" to captureGeneration,"autoStep" to autoStep)
 }
 @Synchronized private fun beginLocalRecognition(kind: String,autoEpoch: Long?): Pair<String,Long>? {
  if(kind !in setOf("ocr","buttons") || !recognitionAvailable())return null
  if(localRecognitionId.isNotEmpty())return null
  if(autoEpoch!=null && (autoEpoch!=captureGeneration || autoStep!=kind ||
    latestLoopFrame?.captureEpoch!=captureGeneration || localRecognitionId.isNotEmpty()))return null
  localRecognitionId=RecognitionEvidence.begin(kind,captureGeneration)
  localRecognitionEpoch=captureGeneration
  localRecognitionUntil=SystemClock.elapsedRealtime()+90000L
  if(autoEpoch!=null){
   autoRun=localRecognitionId
   autoStep="wait"
  } else autoStep="done"
  return Pair(localRecognitionId,captureGeneration)
 }
 @Synchronized private fun localRecognitionLive(id: String)=id.isNotEmpty() && id==localRecognitionId &&
  localRecognitionEpoch==captureGeneration && SystemClock.elapsedRealtime()<localRecognitionUntil &&
  recognitionAvailable()
 @Synchronized private fun endLocalRecognition(id: String){
  if(localRecognitionId!=id)return
  if(autoRun==id){
   autoRun=""
   val (source,state)=RecognitionEvidence.outcome(id) ?: Pair("","")
   autoStep=if(source=="ocr" && state in setOf("done","frame_timeout","inference_timeout","timeout","error") &&
    recognitionAvailable())"buttons" else "done"
  }
  localRecognitionUntil=0L;localRecognitionId=""
 }
 private fun hasLocalDemand(now: Long)=localRecognitionId.isNotEmpty() && localRecognitionEpoch==captureGeneration &&
  now<localRecognitionUntil && RecognitionEvidence.matches(localRecognitionId)
 private fun hasDemand(now: Long)=frameDemand && now-demandAt in 0..8000
 private fun age(now: Long,at: Long)=if(at==0L)-1L else (now-at).coerceAtLeast(0L)
 @Synchronized private fun frameStats(now: Long,enabled: Boolean,demand: Boolean,force: Boolean=false) {
  if(!force && now-statsAt<10000)return
  statsAt=now
  SafeDiagnostics.record(mapOf("event" to "capture_frame_stats","phase" to "frame",
   "source_frames" to sourceFrames.get(),"eligible_frames" to eligibleFrames.get(),"old_frames" to oldFrames.get(),
   "jpeg_reused" to jpegReused.get(),"upload_ok" to uploadOk.get(),"upload_wait" to uploadWait.get(),"upload_error" to uploadError.get(),
   "source_age_ms" to age(now,lastSourceAt),"eligible_age_ms" to age(now,lastEligibleAt),"upload_ms" to uploadMs,
   "refresh_begin" to refreshBegin.get(),"refresh_ok" to refreshOk.get(),"refresh_cancel" to refreshCancel.get(),"refresh_error" to refreshError.get(),
   "sampling_enabled" to enabled,"demand" to demand,"running" to running,"active" to active,
   "source_callbacks" to sourceCallbacks.get(),"callback_age_ms" to age(now,lastCallbackAt),"deferred_callbacks" to deferredCallbacks.get(),
   "status_errors" to statusErrors.get(),"status_age_ms" to age(now,statusOkAt),"http_status" to statusHttp,"capture_state" to captureState,
   "cloud_paused" to recovery.needsAuthorization(),"status_worker_alive" to (statusWorker?.isAlive==true),
   "frame_worker_busy" to (frameWorker.activeCount>0 || frameWorker.queue.isNotEmpty()),"has_status_barrier" to hasStatusBarrier,
   "interactive" to interactive(),"keyguard_locked" to locked()))
 }
 private fun surfaceFailed() {
  refreshError.incrementAndGet()
  SafeDiagnostics.record(mapOf("event" to "capture_stop","phase" to "capture","reason" to "surface_error"))
  endCapture();status="画面取样未能恢复，请重新共享屏幕";stopSelf()
 }
 private val sampleTick=object: Runnable {
  override fun run() {
   if(!running)return
   val now=SystemClock.elapsedRealtime()
   val local=hasLocalDemand(now)
   if(!interactive() || locked())synchronized(this@ScreenShareService) {
    autoStep="done";autoRun=""
    RecognitionEvidence.clearResults()
   }
   val enabled=CaptureSamplingSettings.enabled(this@ScreenShareService) || local
   val demand=hasDemand(now) || local
   frameStats(now,enabled,demand)
   synchronized(this@ScreenShareService) {
    val session=usbOwnerSession
    val d=display;val r=reader;val p=projection
    val sourceSessionValid=if(session==null)local else projectionValid(session)
    val physical=sourceSessionValid && d!=null && r!=null && p!=null && interactive() && !locked()
    val holdDisplay=physical && demand && !recovery.needsAuthorization() && now<until
    displayAwake?.let { if(holdDisplay){if(!it.isHeld)it.acquire(20000L)}else if(it.isHeld)it.release() }
    if(retiredReader!=null && now>=swapDeadline){sampling.restored();surfaceFailed();return}
    if(!burstInFlight() && sampling.begin(now,enabled,demand,physical,(!recovery.needsAuthorization() && (now < until)),
      (frameWorker.activeCount > 0 || frameWorker.queue.isNotEmpty()),lastEligibleAt)) {
     var next: ImageReader?=null
     try {
      next=newReader();swapStartedNanos=System.nanoTime()
      // Both old and new surfaces remain non-null and alive until a real image
      // arrives on the new reader. No deliberate display-off transition.
      d!!.surface=next.surface;retiredReader=r;reader=next;swapDeadline=now+4000L
      refreshBegin.incrementAndGet()
     } catch(_: Exception){next?.close();sampling.restored();surfaceFailed()}
    }
   }
   if(running)handler?.postDelayed(this,500L)
  }
 }

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
 private var displayAwake: PowerManager.WakeLock?=null
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
  latestLoopFrame=null;sequence=0;barrier="";frameGate.replaceAuthorization(System.nanoTime());afterResponse=frameGate.threshold();taskStatus="";frameDemand=false;demandAt=0L
  status="共享已恢复，等待新任务；旧任务不会重放"
  return true
 }
 @Synchronized private fun pauseCloud(capability: String) {
  if(!running || !active || ticket!=capability)return
  SafeDiagnostics.record(mapOf("event" to "capture_pause","phase" to "capture","reason" to "cloud_auth","generation" to recovery.generation()))
  autoStep="done";autoRun="";RecognitionEvidence.clearResults();recovery.pause();latestLoopFrame=null;taskStatus="";frameDemand=false;status="云端授权暂不可用，保留屏幕共享并自动恢复连接"
 }
 @Synchronized private fun endCapture() { handler?.removeCallbacks(burstTick);if(burstPrimary!=null || burstSecondary!=null){display?.release();display=null;closeBurstReaders()};RecognitionEvidence.finish(localRecognitionId,"capture_changed");localRecognitionId="";localRecognitionUntil=0L;captureGeneration++;RecognitionEvidence.clearResults();recovery.stop();running=false;active=false;latestLoopFrame=null;frameDemand=false }
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
    c.connectTimeout=3000;c.readTimeout=3000
    c.setRequestProperty("Authorization","Bearer $requestTicket")
    if(BuildConfig.REMOTE_WORKBENCH_DIAGNOSTICS){
     c.setRequestProperty("X-Pcflash-Workbench",WorkbenchDiagnostics.snapshot(
      sourceFrames.get(),eligibleFrames.get(),uploadOk.get(),uploadError.get()))
    }
    if(BuildConfig.REMOTE_WORKBENCH_DIAGNOSTICS)RecognitionEvidence.envelope()?.let{
     c.setRequestProperty("X-Pcflash-Recognition",it)
    }
    val body=if(supportsLocalResults)synchronized(this@ScreenShareService) {
     if(!recognitionAvailable())RecognitionEvidence.clearResults()
     RecognitionEvidence.localResults(captureGeneration).toString().toByteArray(Charsets.UTF_8)
    } else byteArrayOf()
    CaptureStateHeaders.send(c,captureStateHeadersReader(),body)
    statusHttp=c.responseCode
    if(statusHttp==200) {
     val responseBody=c.inputStream.use { readBounded(it,16385) }
     if(responseBody.size>16384)throw IllegalStateException()
     val data=JSONObject(String(responseBody,Charsets.UTF_8))
     if(running && ticket==requestTicket){
      RecognitionEvidence.acknowledge(data.optJSONObject("recognitionReceipt"))
      RecognitionEvidence.acknowledgeLocal(data.optJSONArray("localResultsReceipt"))
      supportsLocalResults=data.optInt("localResultsProtocol")==1;taskStatus=data.toString();supportsAccessibilityFrames=data.optInt("accessibilityProtocol")==1;supportsOcrFrames=data.optInt("ocrProtocol")==1
      captureState=data.optString("state").let{if(it in setOf("idle","thinking","running","planning","plan","verifying","capturing","done","error","stopped"))it else "unknown"}
      statusOkAt=SystemClock.elapsedRealtime();hasStatusBarrier=Regex("[0-9a-f]{32}").matches(data.optString("barrier")) && data.optString("barrier").any{it!='0'}
      supportsLocalObservation=data.optInt("localObservationProtocol")==1
      val observedBarrier=data.optString("barrier")
      if(supportsLocalObservation && observedBarrier==barrier){val shot=screenshotSize();localObservation.request(data.optJSONObject("localObservationRequest"),observationScope(),shot.first,shot.second,barrier)}
      if(!supportsLocalObservation)localObservation.clear()
      frameDemand=data.optString("state") in setOf("thinking","running","planning","plan","verifying","capturing") && Regex("[0-9a-f]{32}").matches(data.optString("barrier")) && data.optString("barrier").any{it!='0'}
      demandAt=SystemClock.elapsedRealtime()
      if(BuildConfig.SOURCE_BURST_EXPERIMENT)handler?.post { synchronized(this@ScreenShareService){handler?.removeCallbacks(burstTick);burstTick.run()} }
     }
    } else if(CaptureRecoveryGuard.authorizationFailure(statusHttp)) {statusErrors.incrementAndGet();pauseCloud(requestTicket)}
    else if(running){statusErrors.incrementAndGet();status="云端暂不可用，保留共享并重试"}
   } catch(_: Exception) {statusErrors.incrementAndGet();if(running)taskStatus=""} finally {c?.disconnect();statusConnection=null}
   if(running)statusHandler?.postDelayed(this,if(hasDemand(SystemClock.elapsedRealtime()))250L else 2000L)
  }
 }
 private val encodedLock=Any()
 private var encodedFrame: Bitmap?=null
 private var encodedBytes: ByteArray?=null
 private var encodedEpoch=-1L
 private val jpegReused=AtomicLong()

 private fun encodeFrame(frame: Bitmap, epoch: Long): ByteArray? = synchronized(encodedLock) {
  if(!running || epoch!=captureGeneration)return@synchronized null
  val cached=encodedBytes
  if(epoch==encodedEpoch && cached!=null && encodedFrame?.sameAs(frame)==true){
   jpegReused.incrementAndGet()
   return@synchronized cached
  }
  val bytes=ByteArrayOutputStream().use { out -> frame.compress(Bitmap.CompressFormat.JPEG,70,out);out.toByteArray() }
  encodedFrame?.recycle()
  encodedFrame=frame.copy(Bitmap.Config.ARGB_8888,false)
  encodedBytes=bytes
  encodedEpoch=epoch
  bytes
 }

 private val phoneFrameOcr=PhoneFrameOcr()
 private val localObservation=LocalObservationBridge()
 @Volatile private var supportsLocalObservation=false
 private fun observationScope()="$captureGeneration:$barrier"
 private fun screenshotSize(): Pair<Int,Int>{val f=minOf(1.0,720.0/initialWidth,1280.0/initialHeight);return Pair((initialWidth*f).toInt().coerceAtLeast(1),(initialHeight*f).toInt().coerceAtLeast(1))}
 @Volatile private var supportsOcrFrames=false
 @Volatile private var supportsAccessibilityFrames=false
 @Volatile private var supportsLocalResults=false
 private inner class FrameTask(private val bitmap: Bitmap,private val capturedAt: Long,
  private val requestTicket: String,private val uiEpoch: Long,private val localEpoch: Long,private val frameObservationScope: String): Runnable {
  fun discard() { bitmap.recycle() }
  override fun run() {
   var cropped: Bitmap?=null
   var scaled: Bitmap?=null
   try {
    if(!running || ticket!=requestTicket || !frameGate.accept(capturedAt,System.nanoTime()) || recovery.needsAuthorization()){oldFrames.incrementAndGet();return}
    cropped=Bitmap.createBitmap(bitmap,0,0,initialWidth,initialHeight)
    // Encode the entire screen on the upload worker, preserving normalized coordinates.
    val factor=minOf(1.0,720.0/initialWidth,1280.0/initialHeight)
    scaled=if(factor<1.0)Bitmap.createScaledBitmap(cropped!!,(initialWidth*factor).toInt().coerceAtLeast(1),(initialHeight*factor).toInt().coerceAtLeast(1),true) else cropped
    // Identical pixels may reuse encoded bytes; the current capture still
    // advances its own timestamp, barrier, and upload sequence.
    val bytes=encodeFrame(scaled!!,localEpoch) ?: return
    synchronized(this@ScreenShareService) {
     if(running && ticket==requestTicket && localEpoch==captureGeneration && !recovery.needsAuthorization() &&
       frameGate.accept(capturedAt,System.nanoTime()) && bytes.size<=524288) {
      latestLoopFrame=LoopFrame(bytes,scaled!!.width,scaled!!.height,initialWidth,initialHeight,capturedAt,localEpoch)
     }
    }
    if(bytes.size>524288){endCapture();status="画面过大，请降低屏幕分辨率后重新共享";stopSelf();return}
    val tree=if(supportsAccessibilityFrames && barrier.any {it!='0'})AccessibilityAssistService.snapshot(capturedAt,initialWidth,initialHeight,uiEpoch) else null
    val ocr=if(supportsOcrFrames && frameDemand && barrier.any{it!='0'})phoneFrameOcr.scan(scaled!!,bytes,capturedAt) else null
    if(ocr!=null && supportsLocalObservation && frameObservationScope==observationScope()){
     localObservation.report(ocr,capturedAt,frameObservationScope)?.let{ocr.put("v",2).put("local",it)}
    }
    uploadFrame(bytes,capturedAt,requestTicket,tree,ocr)
   } catch(_: Exception) {if(running && ticket==requestTicket)status="画面编码失败，正在重试"}
   finally {if(scaled!==cropped)scaled?.recycle();if(cropped!==bitmap)cropped?.recycle();bitmap.recycle()}
  }
 }
 private fun uploadFrame(bytes: ByteArray,capturedAt: Long,requestTicket: String,tree: JSONObject?,ocr: JSONObject?) {
  val requestBarrier: String
  val requestSequence: Int
  synchronized(this) {
   if(!running || ticket!=requestTicket || recovery.needsAuthorization() ||
      !frameGate.accept(capturedAt,System.nanoTime()) || SystemClock.elapsedRealtime()>=until)return
   requestBarrier=barrier;requestSequence=++sequence
  }
  // Negotiate optional metadata via /status; old servers continue receiving JPEG.
  // No second request can mix a UI tree with a different frame or barrier.
  val envelope=if(tree==null && ocr==null)null else JSONObject().put("jpegBase64",android.util.Base64.encodeToString(bytes,android.util.Base64.NO_WRAP)).also{
   if(tree!=null)it.put("accessibility",tree)
   if(ocr!=null)it.put("ocr",ocr)
  }
  val body=envelope?.toString()?.toByteArray(Charsets.UTF_8)?:bytes
  val contentType=if(envelope==null)"image/jpeg" else "application/vnd.pcflash.screen+json"
  val uploadStarted=SystemClock.elapsedRealtime()
  var uploadOutcome=0
  try {
     val conn=URL("$BASE/frame").openConnection() as HttpsURLConnection
     connection=conn;conn.requestMethod="POST";conn.connectTimeout=5000;conn.readTimeout=5000;conn.doOutput=true
     conn.setRequestProperty("X-Screen-Native-Width",initialWidth.toString());conn.setRequestProperty("X-Screen-Native-Height",initialHeight.toString());conn.setRequestProperty("X-Screen-Barrier",requestBarrier);conn.setRequestProperty("Authorization","Bearer $requestTicket");conn.setRequestProperty("Content-Type",contentType);conn.setRequestProperty("X-Screen-Sequence",requestSequence.toString());conn.setFixedLengthStreamingMode(body.size)
     conn.outputStream.use{it.write(body)}
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
       barrier=next;frameGate.changeBarrier(next,System.nanoTime());afterResponse=frameGate.threshold()
      }
      uploadOutcome=code
      val activeFrame=next.any { it!='0' } && (code==200 || response.optString("reason") in listOf("capture barrier required","superseded frame"))
      fastFramesUntil=if(activeFrame)SystemClock.elapsedRealtime()+2500L else 0L
      if(running)status=if(code==200)"画面传输：已上传" else "画面传输：共享中"
     } else if(CaptureRecoveryGuard.authorizationFailure(code)) {pauseCloud(requestTicket)}
     else {status="画面上传暂不可用，保留共享并重试"}
     conn.disconnect();connection=null
  } catch(_: Exception) {if(running && ticket==requestTicket)status="画面上传失败，正在重试"}
  finally {if(uploadOutcome==200)uploadOk.incrementAndGet() else if(uploadOutcome==202)uploadWait.incrementAndGet() else uploadError.incrementAndGet();uploadMs=SystemClock.elapsedRealtime()-uploadStarted;connection?.disconnect();connection=null}
 }
 private fun drainSource() {
  synchronized(this) {
   if(!running)return
   val source=reader?:return
   val image=try{source.acquireLatestImage()}catch(_: Exception){return} ?: return
   var bitmap: Bitmap?=null
    try {
     val now=SystemClock.elapsedRealtime()
     sourceFrames.incrementAndGet();lastSourceAt=now
     if(!running)return
     @Suppress("DEPRECATION") val currentDisplay=(getSystemService(WINDOW_SERVICE) as WindowManager).defaultDisplay
     val currentSize=Point();currentDisplay.getRealSize(currentSize)
     if(currentDisplay.rotation!=initialRotation || currentSize.x!=initialWidth || currentSize.y!=initialHeight){geometryChanged();return}
     if(image.width!=initialWidth || image.height!=initialHeight){geometryChanged();return}
     // Confirm physical reader recovery independently of cloud/frame admission.
     if(retiredReader!=null && source===reader && image.timestamp>swapStartedNanos){
      retiredReader?.close();retiredReader=null;swapStartedNanos=0L;sampling.restored();refreshOk.incrementAndGet()
     }
     if(!frameGate.accept(image.timestamp,System.nanoTime()) || image.timestamp<=lastEligibleTimestamp){oldFrames.incrementAndGet();return}
     if(burstInFlight()){
      val burst=sourceBurst!!
      val scope=observationScope()
      if(scope!=burstScope || !burstAuthorized()){
       burst.tick(System.nanoTime(),scope,false,false,locked(),false);return
      }
      // Admit an acquired valid image before the independently scheduled switch tick.
      // image() enforces the absolute deadline even if the handler tick is delayed.
      if(!running || source!==reader || !burst.image(source===burstSecondary,image.timestamp,System.nanoTime()))return
     }
     lastEligibleTimestamp=image.timestamp;lastEligibleAt=now;eligibleFrames.incrementAndGet()
     if(now>=until)pauseCloud(ticket)
     if(recovery.needsAuthorization())return
     val requestTicket=ticket
     last=now
     val plane=image.planes[0];val padding=plane.rowStride-plane.pixelStride*image.width
     val frameObservationScope=observationScope()
     if(supportsLocalObservation && frameDemand && barrier.any{it!='0'}){
      val shot=screenshotSize()
      try{localObservation.sample(frameObservationScope,eligibleFrames.get(),image.timestamp,plane.buffer.duplicate(),image.width,image.height,plane.pixelStride,plane.rowStride,shot.first,shot.second)}catch(_: Exception){localObservation.clear()}
     }else localObservation.clear()
     bitmap=Bitmap.createBitmap(image.width+padding/plane.pixelStride,image.height,Bitmap.Config.ARGB_8888)
     bitmap!!.copyPixelsFromBuffer(plane.buffer)
     frameWorker.execute(FrameTask(bitmap!!,image.timestamp,requestTicket,AccessibilityAssistService.epoch(),captureGeneration,frameObservationScope))
     bitmap=null // Ownership moved to the bounded uploader; rejected frames are recycled.

    } catch(e: Exception) {if(running)status="画面上传失败，正在重试"}
    finally {bitmap?.recycle();image.close()}
  }
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
   reader=newReader()
   until=SystemClock.elapsedRealtime()+270000L;recovery.start();running=true;current=this;taskStatus="";statusHandler!!.post(poll);status="共享中，等待语音任务"
   val power=getSystemService(POWER_SERVICE) as PowerManager
   keepAwake=power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"pcflash:ScreenShareCpu")
   keepAwake!!.setReferenceCounted(false);keepAwake!!.acquire()
   // Hold an already-awake display only while a fresh authorized task needs it.
   // Idle sharing respects the user's timeout and never overrides brightness.
   displayAwake=power.newWakeLock(PowerManager.SCREEN_BRIGHT_WAKE_LOCK,"pcflash:ScreenShareActiveTask")
   displayAwake!!.setReferenceCounted(false)
   display=projection!!.createVirtualDisplay("AI phone screen",width,height,metrics.densityDpi,DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,reader!!.surface,null,handler)
   handler!!.post(sampleTick)
  } catch(e: Exception) {status="屏幕共享启动失败，请重新授权";stopSelf()}
  return START_NOT_STICKY
 }
 override fun onTaskRemoved(rootIntent: Intent?) {
  // USB attach uses a temporary task; losing that task is not consent revocation.
  SafeDiagnostics.record(mapOf("event" to "capture_task_removed","phase" to "capture","reason" to "task_removed","generation" to recovery.generation(),"active" to active,"running" to running))
  super.onTaskRemoved(rootIntent)
 }
 override fun onDestroy() {
  phoneFrameOcr.close();localObservation.clear()
  synchronized(encodedLock) {
   encodedEpoch=-1L
   encodedFrame?.recycle();encodedFrame=null;encodedBytes=null
  }
  SafeDiagnostics.record(mapOf("event" to "capture_destroy","phase" to "capture","reason" to "destroy","generation" to recovery.generation(),"active" to active,"running" to running))
  endCapture()
  synchronized(this) {
   if(current===this)current=null
   active=false;usbOwnerSerial=null;usbOwnerSession=null
   running=false
  }
  renewalConnection?.disconnect();connection?.disconnect();statusConnection?.disconnect();frameWorker.shutdownNow().forEach { (it as? FrameTask)?.discard() }
  val old=synchronized(this) {
   display?.release();display=null;closeBurstReaders();reader?.close();reader=null
   if(retiredReader!=null)refreshCancel.incrementAndGet();retiredReader?.close();retiredReader=null
   displayAwake?.let{if(it.isHeld)it.release()};displayAwake=null
   keepAwake?.let{if(it.isHeld)it.release()};keepAwake=null
   val previous=projection;projection=null;previous
  }
  old?.stop();worker?.quitSafely();worker=null
  handler?.removeCallbacksAndMessages(null);statusHandler?.removeCallbacksAndMessages(null);statusWorker?.quitSafely();statusWorker=null;statusHandler=null;displayManager?.unregisterDisplayListener(displayListener)
  taskStatus=""
  val capability=ticket;ticket="";revoke(capability)
  stopForeground(STOP_FOREGROUND_REMOVE);super.onDestroy()
 }
}

/** Latest encoded shared frame kept for the local auto-loop (on-device ONNX). */
class LoopFrame(val jpeg: ByteArray,val width: Int,val height: Int,val nativeWidth: Int,val nativeHeight: Int,val capturedAt: Long,val captureEpoch: Long)
