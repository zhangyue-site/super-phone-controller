package org.example.phonecontroller

import android.app.*
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.*
import java.io.ByteArrayOutputStream
import java.net.URL
import javax.net.ssl.HttpsURLConnection

class ScreenShareService: Service() {
 companion object { @Volatile var status="未共享"; private const val BASE="https://controller.example.invalid/phone-controller/app-screen" }
 private var projection: MediaProjection?=null
 private var display: VirtualDisplay?=null
 private var reader: ImageReader?=null
 private var worker: HandlerThread?=null
 private var handler: Handler?=null
 @Volatile private var running=false
 @Volatile private var connection: HttpsURLConnection?=null
 private var ticket=""
 private var sequence=0
 private var last=0L
 private var until=0L
 override fun onBind(intent: Intent?)=null
 override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
  if(intent?.action=="STOP"){status="已停止共享";stopSelf();return START_NOT_STICKY}
  if(running){stopSelf();return START_NOT_STICKY}
  val value=intent?.getStringExtra("ticket")
  @Suppress("DEPRECATION") val grant=intent?.getParcelableExtra<Intent>("grant")
  if(value==null || grant==null){stopSelf();return START_NOT_STICKY}
  ticket=value
  val nm=getSystemService(NOTIFICATION_SERVICE) as NotificationManager
  if(Build.VERSION.SDK_INT>=26)nm.createNotificationChannel(NotificationChannel("screen", "AI屏幕共享", NotificationManager.IMPORTANCE_LOW))
  val stop=PendingIntent.getService(this,0,Intent(this,ScreenShareService::class.java).setAction("STOP"),PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
  val builder=if(Build.VERSION.SDK_INT>=26)Notification.Builder(this,"screen") else Notification.Builder(this)
  val notification=builder.setSmallIcon(android.R.drawable.ic_menu_view).setContentTitle("正在向你的AI共享屏幕").setContentText("手机操作由控制板HID完成；点此停止共享").setOngoing(true).setContentIntent(stop).addAction(android.R.drawable.ic_menu_close_clear_cancel,"停止",stop).build()
  if(Build.VERSION.SDK_INT>=29)startForeground(71,notification,ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION) else startForeground(71,notification)
  try {
   worker=HandlerThread("screen-capture").also{it.start()};handler=Handler(worker!!.looper)
   projection=(getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager).getMediaProjection(Activity.RESULT_OK,grant)
   projection!!.registerCallback(object: MediaProjection.Callback(){override fun onStop(){status="系统已停止共享";stopSelf()}},Handler(Looper.getMainLooper()))
   val metrics=resources.displayMetrics
   val scale=720.0/metrics.widthPixels.coerceAtLeast(metrics.heightPixels)
   val width=(metrics.widthPixels*scale.coerceAtMost(1.0)).toInt().coerceAtLeast(1)
   val height=(metrics.heightPixels*scale.coerceAtMost(1.0)).toInt().coerceAtLeast(1)
   reader=ImageReader.newInstance(width,height,PixelFormat.RGBA_8888,2)
   running=true;until=SystemClock.elapsedRealtime()+270000L;status="共享中，等待语音任务"
   reader!!.setOnImageAvailableListener({ source ->
    val image=source.acquireLatestImage() ?: return@setOnImageAvailableListener
    var bitmap: Bitmap?=null
    var cropped: Bitmap?=null
    try {
     val now=SystemClock.elapsedRealtime()
     if(!running)return@setOnImageAvailableListener
     if(now>=until){status="共享凭证已到期，请重新开启";stopSelf();return@setOnImageAvailableListener}
     if(now-last<800)return@setOnImageAvailableListener
     last=now
     val plane=image.planes[0];val padding=plane.rowStride-plane.pixelStride*image.width
     bitmap=Bitmap.createBitmap(image.width+padding/plane.pixelStride,image.height,Bitmap.Config.ARGB_8888)
     bitmap!!.copyPixelsFromBuffer(plane.buffer)
     cropped=Bitmap.createBitmap(bitmap!!,0,0,image.width,image.height)
     val bytes=ByteArrayOutputStream().use { out -> cropped!!.compress(Bitmap.CompressFormat.JPEG,70,out);out.toByteArray() }
     if(bytes.size>524288)return@setOnImageAvailableListener
     val conn=URL("$BASE/frame").openConnection() as HttpsURLConnection
     connection=conn;conn.requestMethod="POST";conn.connectTimeout=5000;conn.readTimeout=5000;conn.doOutput=true
     conn.setRequestProperty("Authorization","Bearer $ticket");conn.setRequestProperty("Content-Type","image/jpeg");conn.setRequestProperty("X-Screen-Sequence",(++sequence).toString());conn.setFixedLengthStreamingMode(bytes.size)
     conn.outputStream.use{it.write(bytes)}
     val code=conn.responseCode
     if(code==200)status="屏幕已上传，AI可读取当前任务画面" else if(code==202)status="共享中，等待语音任务" else {status="共享授权失效，请重新开启";stopSelf()}
     conn.disconnect();connection=null
    } catch(e: Exception) {if(running)status="画面上传失败，正在重试"}
    finally {if(cropped!==bitmap)cropped?.recycle();bitmap?.recycle();image.close();connection?.disconnect();connection=null}
   },handler)
   display=projection!!.createVirtualDisplay("AI phone screen",width,height,metrics.densityDpi,DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,reader!!.surface,null,handler)
  } catch(e: Exception) {status="屏幕共享启动失败，请重新授权";stopSelf()}
  return START_NOT_STICKY
 }
 override fun onDestroy() {
  running=false;connection?.disconnect()
  display?.release();display=null;reader?.close();reader=null
  val old=projection;projection=null;old?.stop();worker?.quitSafely();worker=null
  val capability=ticket;ticket=""
  if(capability.isNotEmpty())Thread {
   try {
    val c=URL("$BASE/stop").openConnection() as HttpsURLConnection
    c.requestMethod="POST";c.connectTimeout=3000;c.readTimeout=3000;c.doOutput=true;c.setRequestProperty("Authorization","Bearer $capability");c.setFixedLengthStreamingMode(0);c.outputStream.close();c.responseCode;c.disconnect()
   } catch(_: Exception) { }
  }.start()
  stopForeground(STOP_FOREGROUND_REMOVE);super.onDestroy()
 }
}
