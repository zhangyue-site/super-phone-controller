package org.example.phonecontroller

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import java.util.Collections
import java.util.LinkedHashSet

/**
 * 被控端前台保活服务（vc90）。
 *
 * MIUI 灭屏后会把没有前台组件的进程挂起：云端轮询停摆、USB 插拔广播丢失，
 * 磨账链在「任务等待/执行」窗口整条死锁。本服务在任务窗口内以 specialUse
 * 前台服务 + partial WakeLock 保持进程与 CPU 运行，灭屏也继续引擎轮询；
 * 窗口结束（计数归零）即退出，不留常驻。
 *
 * 持有方（hold/release 引用计数，均幂等）：
 * - ScreenShareService 生命周期（共享/执行窗口）；
 * - UsbLaunchBridge expectMode（板端模式切换等待窗口）；
 * - Dart 控制会话（pcflash/app 的 keepaliveHold/keepaliveRelease，授权后到关闭）。
 */
class EngineKeepaliveService : Service() {
 override fun onBind(intent: Intent?): IBinder? = null
 override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
  val nm=getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
  if(Build.VERSION.SDK_INT>=26)nm.createNotificationChannel(NotificationChannel("keepalive","被控运行中",NotificationManager.IMPORTANCE_LOW))
  val builder=if(Build.VERSION.SDK_INT>=26)Notification.Builder(this,"keepalive") else @Suppress("DEPRECATION") Notification.Builder(this)
  val notification=builder.setSmallIcon(android.R.drawable.ic_dialog_info)
   .setContentTitle("被控运行中").setContentText("任务执行期间保持连接与轮询")
   .setOngoing(true).build()
  if(Build.VERSION.SDK_INT>=34)startForeground(NOTIFY_ID,notification,ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE) else startForeground(NOTIFY_ID,notification)
  return START_NOT_STICKY
 }
 companion object {
  private const val NOTIFY_ID=72
  private const val STOP_DEBOUNCE_MS=800L
  private val holds: MutableSet<String> = Collections.synchronizedSet(LinkedHashSet())
  @Volatile private var wakeLock: PowerManager.WakeLock?=null
  @Volatile private var wifiLock: WifiManager.WifiLock?=null
  private val ui=Handler(Looper.getMainLooper())
  private val stopCheck=Runnable {
   if(holds.isEmpty()) {
    wakeLock?.let{if(it.isHeld)it.release()};wakeLock=null
    wifiLock?.let{if(it.isHeld)it.release()};wifiLock=null
    SafeDiagnostics.record(mapOf("event" to "keepalive_stop","phase" to "keepalive"))
   }
  }
  /** 任务窗口开始。持 partial WakeLock + WifiLock；前台服务启动失败（后台限制）仅降级记录。 */
  fun hold(context: Context,tag: String) {
   val app=context.applicationContext
   if(!holds.add(tag))return
   SafeDiagnostics.record(mapOf("event" to "keepalive_hold","phase" to "keepalive","tag" to tag,"count" to holds.size))
   ui.removeCallbacks(stopCheck)
   try {
    if(wakeLock==null) {
     val power=app.getSystemService(Context.POWER_SERVICE) as PowerManager
     val lock=power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"pcflash:EngineKeepalive")
     lock.setReferenceCounted(false);lock.acquire()
     wakeLock=lock
    }
   } catch(e: Exception) {
    SafeDiagnostics.record(mapOf("event" to "keepalive_wakelock_failed","phase" to "keepalive","reason" to (e.message?:"wake")))
   }
   try {
    if(wifiLock==null) {
     val wifi=app.getSystemService(Context.WIFI_SERVICE) as? WifiManager
     if(wifi!=null) {
      @Suppress("DEPRECATION")
      val lock=wifi.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF,"pcflash:EngineKeepaliveWifi")
      lock.setReferenceCounted(false);lock.acquire()
      wifiLock=lock
     }
    }
   } catch(e: Exception) {
    // Wi-Fi lock is best effort; a partial WakeLock still keeps the poller alive.
    SafeDiagnostics.record(mapOf("event" to "keepalive_wifilock_failed","phase" to "keepalive","reason" to (e.message?:"wifi")))
   }
   if(holds.size==1) {
    try {
     val intent=Intent(app,EngineKeepaliveService::class.java)
     if(Build.VERSION.SDK_INT>=26)app.startForegroundService(intent) else app.startService(intent)
    } catch(e: Exception) {
     // 前台启动被后台限制拦截：WakeLock 已兜底，链路仍不中断。
     SafeDiagnostics.record(mapOf("event" to "keepalive_foreground_failed","phase" to "keepalive","reason" to (e.message?:"start")))
    }
   }
  }
  /** 任务窗口结束。计数归零后短暂延迟退出，吸收连续动作间的抖动。 */
  fun release(context: Context,tag: String) {
   if(!holds.remove(tag))return
   SafeDiagnostics.record(mapOf("event" to "keepalive_release","phase" to "keepalive","tag" to tag,"count" to holds.size))
   if(holds.isEmpty())ui.postDelayed(stopCheck,STOP_DEBOUNCE_MS)
  }
 }
}
