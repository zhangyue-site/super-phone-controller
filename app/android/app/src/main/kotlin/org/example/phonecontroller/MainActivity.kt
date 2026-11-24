package org.example.phonecontroller

import android.app.Activity
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.media.projection.MediaProjectionConfig
import android.net.Uri
import android.os.Build
import android.os.SystemClock
import android.os.Bundle
import android.provider.Settings
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity: FlutterActivity() {
 private val billTextLoop by lazy { BillTextLoop(applicationContext) }
 private var imeRemoteToken: Long? = null
 private var usbProof: UsbProofBridge? = null
 private var pending: MethodChannel.Result? = null
 private var ticket: String? = null
 private var pendingUsbSession: String? = null
 private var consentInFlight=false
 private var pendingRequestCode=-1
 private fun nextConsentCode(): Int {
  val prefs=getSharedPreferences("usb-boards",MODE_PRIVATE)
  val code=prefs.getInt("__consent-code",1000).coerceIn(1000,65000)
  if(!prefs.edit().putInt("__consent-code",if(code>=65000)1000 else code+1).commit())throw IllegalStateException("无法保存授权会话")
  return code
 }
 private fun guardedAccessibilityInput(action: () -> Boolean): Boolean {
  val token = RelayInputOwner.tryBeginRemote(applicationContext) ?: return false
  return try { action() } finally { RelayInputOwner.endRemote(token) }
 }
 override fun onCreate(savedInstanceState: Bundle?) {
  super.onCreate(savedInstanceState)
        ensureAdbAutoEnable()
  UsbLaunchBridge.accept(intent)
 }
 override fun onNewIntent(intent: Intent) {
  super.onNewIntent(intent);setIntent(intent);UsbLaunchBridge.accept(intent)
 }
 private fun cancelUsbConsent(value: String) {
  if(pendingUsbSession!=value)return
  ticket?.let { ScreenShareService.revoke(it) };ticket=null;pendingUsbSession=null
  pending?.error("usb_detached","控制板已拔出，请重新插入后共享",null);pending=null
  // Keep consentInFlight until its result arrives; never hand an old result to a new request.
 }

 override fun configureFlutterEngine(engine: FlutterEngine) {
  RelayIme.recoverIfStuck(applicationContext)
  super.configureFlutterEngine(engine)
  SafeDiagnostics.initialize(this)
  WorkbenchDiagnostics.record("plugins",0,
   if(engine.plugins.has(com.jmx.flutter_blue_plus.FlutterBluePlusPlugin::class.java))1 else 0)
  UsbLaunchBridge.initialize(this)
  usbProof?.close();usbProof=UsbProofBridge(applicationContext)
  val usb=MethodChannel(engine.dartExecutor.binaryMessenger,"pcflash/usb")
  UsbLaunchBridge.attachOwner(this,{ usb.invokeMethod("changed",it) },{ cancelUsbConsent(it) })
  usb.setMethodCallHandler { call,result ->
   when(call.method) {
    "info", "sign" -> usbProof!!.request(call.method,call.argument("session"),call.argument("nonce"),result)
    "snapshot" -> result.success(UsbLaunchBridge.snapshot())
    "expectMode" -> {
     val hid=call.argument<Boolean>("hid")
     if(!consentInFlight && pending==null && hid!=null && UsbLaunchBridge.expectMode(call.argument("session"),hid))result.success(null)
     else result.error("usb_mode_rejected","USB连接已改变或正在切换，请重新连接",null)
    }
    "bind" -> if(UsbLaunchBridge.bind(call.argument("session"),call.argument("remoteId"),call.argument("deviceId")))result.success(null) else result.error("usb_detached","USB连接已改变，未保存配对",null)
    "forget" -> if(UsbLaunchBridge.forget(call.argument("session")))result.success(null) else result.error("busy","请先停止共享并保持USB连接后重新配对",null)
    else -> result.notImplemented()
   }
  }
  MethodChannel(engine.dartExecutor.binaryMessenger,"pcflash/local-loop").setMethodCallHandler { call,result ->
   when(call.method) {
    "startBillOcr" -> result.success(billTextLoop.start(call.argument<Boolean>("delayed")==true,call.argument<Number>("autoEpoch")?.toLong()))
    "stopBillOcr" -> { billTextLoop.stop();result.success(null) }
    "billOcrStatus" -> result.success(billTextLoop.status)
    "recognitionStatus" -> result.success(RecognitionEvidence.status()+ScreenShareService.autoRecognitionStatus())
    "beginButtonRecognition" -> {
     val lease=ScreenShareService.beginRecognition("buttons",call.argument<Number>("autoEpoch")?.toLong())
     if(lease==null)result.error("recognition_unavailable","请先开启共享，或停止上一轮识别",null)
     else {WorkbenchDiagnostics.beginRecognition();result.success(mapOf("run" to lease.first,"epoch" to lease.second,"afterFrame" to System.nanoTime()))}
    }
    "endButtonRecognition" -> {
     val id=call.argument<String>("run")?:""
     val reason=call.argument<String>("reason")?:"stopped"
     RecognitionEvidence.finish(id,if(reason in setOf("done","stopped","error","frame_timeout","timeout"))reason else "error")
     ScreenShareService.endRecognition(id);result.success(null)
    }
    "recordButtonRecognition" -> {
     val id=call.argument<String>("run")?:""
     val stamp=call.argument<Number>("frameId")?.toLong()?:-1L
     val epoch=call.argument<Number>("epoch")?.toLong()?:-1L
     val width=call.argument<Int>("width")?:0;val height=call.argument<Int>("height")?:0
     val ms=call.argument<Int>("ms")?:0
     val age=call.argument<Number>("age")?.toLong()?:-1L
     val boxes=call.argument<Int>("boxes")
     if(boxes!=null && boxes !in 0..2100){result.error("recognition_invalid","无效的按钮结果",null);return@setMethodCallHandler}
     if(age !in 0..2500 || !ScreenShareService.recognitionLive(id) || RecognitionEvidence.source()!="buttons")
      result.error("recognition_expired","共享会话已改变，本轮已停止",null)
     else result.success(RecognitionEvidence.frame(id,LoopFrame(byteArrayOf(),width,height,width,height,stamp,epoch),age,ms,boxes?:0,"buttons",boxes=boxes))
    }
    "diagnostic" -> {
     WorkbenchDiagnostics.record(call.argument<String>("stage"),call.argument<Int>("count"),
      call.argument<Int>("value"))
     result.success(null)
    }
    "latestFrame" -> {
     val f=ScreenShareService.latestLoopFrame
     val run=call.argument<String>("run")
     if(run!=null && !ScreenShareService.recognitionLive(run))
      result.error("recognition_expired","共享会话已结束，本轮已停止",null)
     else if(f==null || !ScreenShareService.active)result.success(mapOf("available" to false))
     else result.success(mapOf("available" to true,"jpeg" to f.jpeg,"width" to f.width,"height" to f.height,
      "nativeWidth" to f.nativeWidth,"nativeHeight" to f.nativeHeight,
      "captureEpoch" to f.captureEpoch,"frameId" to f.capturedAt, "ageMs" to ((System.nanoTime()-f.capturedAt)/1_000_000L)))
    }
    else -> result.notImplemented()
   }
  }
  MethodChannel(engine.dartExecutor.binaryMessenger,"pcflash/capture-sampling").setMethodCallHandler { call,result ->
   when(call.method) {
    "status" -> result.success(mapOf("enabled" to CaptureSamplingSettings.enabled(this)))
    "setEnabled" -> {
     val enabled=call.argument<Boolean>("enabled")
     if(enabled==null || !CaptureSamplingSettings.setEnabled(this,enabled))result.error("storage_failed","取样设置未保存",null)
     else result.success(mapOf("enabled" to CaptureSamplingSettings.enabled(this)))
    }
    else -> result.notImplemented()
   }
  }
  MethodChannel(engine.dartExecutor.binaryMessenger,"pcflash/accessibility").setMethodCallHandler { call,result ->
   when(call.method) {
    "status" -> result.success(AccessibilityAssistService.status(this))
    "setEnabled" -> {
     val enabled=call.argument<Boolean>("enabled")
     if(enabled==null || !AccessibilityAssistService.setEnabled(this,enabled))result.error("storage_failed","辅助设置未保存",null)
     else result.success(AccessibilityAssistService.status(this))
    }
    "openSettings" -> {
     try {startActivity(AccessibilityAssistService.settingsIntent());result.success(null)}
     catch(_: Exception) {result.error("settings_unavailable","无法打开无障碍设置，请从系统设置进入",null)}
    }
    "setText" -> result.success(guardedAccessibilityInput { AccessibilityAssistService.setText(this,call.argument<String>("text")?:"") })
    "clickLabel" -> result.success(guardedAccessibilityInput { AccessibilityAssistService.clickLabel(this,call.argument<String>("label")?:"") })
    else -> result.notImplemented()
   }
  }
  MethodChannel(engine.dartExecutor.binaryMessenger,"pcflash/ime").setMethodCallHandler { call,result ->
   when(call.method) {
    "status" -> result.success(RelayIme.status(applicationContext))
    "beginRemote" -> {
     val token = RelayInputOwner.tryBeginRemote(applicationContext)
     if (token != null) imeRemoteToken = token
     result.success(token)
    }
    "permitsRemote" -> {
     val token = call.argument<Number>("token")?.toLong()
     result.success(token != null && token == imeRemoteToken && RelayInputOwner.permits(applicationContext, token))
    }
    "endRemote" -> {
     val token = call.argument<Number>("token")?.toLong()
     if (token != null && token == imeRemoteToken) {
      RelayInputOwner.endRemote(token)
      imeRemoteToken = null
     }
     result.success(null)
    }
    "cancelVoiceForStop" -> { RelayImeService.instance?.cancelVoiceForStop(); result.success(null) }
    "resumeRemote" -> result.success(RelayInputOwner.resumeRemote(applicationContext))
    "activate" -> result.success(RelayIme.activate(applicationContext) ?: "")
    "restore" -> { RelayIme.restore(applicationContext, call.argument<String>("id") ?: ""); result.success(true) }
    "pasteText" -> {
     val text=call.argument<String>("text") ?: ""
     if(text.isEmpty()){result.error("bad_args","text required",null);return@setMethodCallHandler}
     val enter=call.argument<Boolean>("enter") ?: false
     val timeoutMs=(call.argument<Number>("timeoutMs") ?: 8000).toLong()
     val token = call.argument<Number>("token")?.toLong()
     if (token == null || token != imeRemoteToken || !RelayInputOwner.permits(applicationContext,token)) {
      result.success(mapOf("ok" to false,"reason" to "manual_or_busy"))
      return@setMethodCallHandler
     }
     RelayIme.paste(applicationContext,text,enter,timeoutMs,remoteToken=token){ ok,reason ->
      result.success(mapOf("ok" to ok,"reason" to (reason ?: "")))
     }
    }
    else -> result.notImplemented()
   }
  }
  MethodChannel(engine.dartExecutor.binaryMessenger, "pcflash/app").setMethodCallHandler { call, result ->
   when(call.method) {
    "adbGuideStatus" -> {
     val s = AccessibilityAssistService.guideStatus(this).toMutableMap()
     s["debugPort"] = wirelessDebugPort()
     result.success(s)
    }
    "adbGuideArm" -> { AccessibilityAssistService.guideArm(this, auto = false); result.success(null) }
    "diagnosticEvent" -> { SafeDiagnostics.record(call.arguments as? Map<*,*> ?: emptyMap<Any,Any>());result.success(null) }
    "diagnostics" -> { ScreenShareService.recordDiagnosticSnapshot();result.success(SafeDiagnostics.read()) }
    "readControllerPairing", "saveControllerPairing", "clearControllerPairing" -> {
     try {
      val store = ControllerPairingStorage(noBackupFilesDir)
      when (call.method) {
       "readControllerPairing" -> result.success(store.read())
       "saveControllerPairing" -> { store.save(requireNotNull(call.argument<String>("value"))); result.success(null) }
       else -> { store.clear(); result.success(null) }
      }
     } catch (_: Exception) {
      result.error("pairing_storage", "无法访问本机配对存储", null)
     }
    }
    "appearance" -> result.success(getSharedPreferences("appearance",MODE_PRIVATE).getString("mode","system"))
    "setAppearance" -> {
     val mode=call.argument<String>("mode")
     if(mode !in setOf("system","light","dark"))result.error("invalid_mode","主题设置无效",null)
     else if(getSharedPreferences("appearance",MODE_PRIVATE).edit().putString("mode",mode).commit())result.success(null)
     else result.error("storage_failed","主题设置未保存",null)
    }
    "info" -> {
     @Suppress("DEPRECATION")
     val info=packageManager.getPackageInfo(packageName,0)
     @Suppress("DEPRECATION")
     val code=if(Build.VERSION.SDK_INT>=28) info.longVersionCode else info.versionCode.toLong()
     result.success(mapOf("versionName" to info.versionName, "versionCode" to code))
    }
    "openDownload" -> {
     if(BuildConfig.DOWNLOAD_URL.isBlank()){result.error("not_configured","更新入口尚未配置，请联系应用维护者",null);return@setMethodCallHandler}
     try {
      startActivity(Intent(Intent.ACTION_VIEW,Uri.parse(BuildConfig.DOWNLOAD_URL)))
      result.success(null)
     } catch(_: Exception) { result.error("browser_unavailable","无法打开官方下载页",null) }
    }
    "keepaliveHold" -> { EngineKeepaliveService.hold(this,call.argument<String>("tag") ?: "task");result.success(null) }
    "keepaliveRelease" -> { EngineKeepaliveService.release(this,call.argument<String>("tag") ?: "task");result.success(null) }
    else -> result.notImplemented()
   }
  }
  MethodChannel(engine.dartExecutor.binaryMessenger, "pcflash/screen").setMethodCallHandler { call, result ->
   when(call.method) {
    "start" -> {
     if(BuildConfig.CONTROLLER_BASE_URL.isBlank()){result.error("not_configured","服务地址尚未配置，请联系应用维护者",null);return@setMethodCallHandler}
     val value=call.argument<String>("ticket")
     val requestedUsb=call.argument<String>("usbSession")
     if(consentInFlight || pending!=null || ScreenShareService.active || value==null || !Regex("[A-Za-z0-9_-]{43}").matches(value)) {
      result.error("busy", "共享正在准备或凭证无效", null)
     } else if(requestedUsb!=null && !UsbLaunchBridge.matches(requestedUsb)) {
      ScreenShareService.revoke(value);result.error("usb_detached","控制板已拔出，请重新插入",null)
     } else {
      pending=result;ticket=value;pendingUsbSession=requestedUsb;consentInFlight=true
      val manager=getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
      try {
       val consent = if(Build.VERSION.SDK_INT>=34) manager.createScreenCaptureIntent(MediaProjectionConfig.createConfigForDefaultDisplay()) else manager.createScreenCaptureIntent()
       pendingRequestCode=nextConsentCode()
       startActivityForResult(consent, pendingRequestCode)
      } catch(_: Exception) {
       pending=null;ticket=null;pendingUsbSession=null;consentInFlight=false;ScreenShareService.revoke(value)
       result.error("permission_failed", "无法请求屏幕共享，请重新开启", null)
      }
     }
    }
    "stop" -> {
     SafeDiagnostics.record(mapOf("event" to "capture_stop","phase" to "capture","reason" to "flutter_stop"))
     val requestedUsb=call.argument<String>("usbSession")
     // An old widget's cleanup must not cancel another USB generation's consent or capture.
     if(requestedUsb==null || requestedUsb==pendingUsbSession) {
      pendingUsbSession=null;ticket?.let { ScreenShareService.revoke(it) };ticket=null
      pending?.error("cancelled","已取消屏幕共享",null);pending=null
     }
     if(requestedUsb==null || requestedUsb==ScreenShareService.usbOwnerSession) {
      RelayImeService.instance?.cancelVoiceForStop()
      imeRemoteToken?.let { RelayInputOwner.endRemote(it) }; imeRemoteToken = null
      ScreenShareService.status="已停止共享";ScreenShareService.taskStatus=""
      ScreenShareService.stopRecovery()
      stopService(Intent(this,ScreenShareService::class.java))
     }
     result.success(null)
    }
    "captureSession" -> {
     val session=call.argument<String>("usbSession")
     val value=if(session==null)null else ScreenShareService.captureSession(session)
     if(value==null)result.error("capture_session_invalid","屏幕共享会话已结束",null) else result.success(value)
    }
    "replaceUsbCapture" -> {
     val session=call.argument<String>("usbSession");val serial=call.argument<String>("serial")
     val generation=call.argument<Number>("generation")?.toLong();val capability=call.argument<String>("ticket")
     if(session!=null && serial!=null && generation!=null && capability!=null) {
      ScreenShareService.replaceUsbCapture(session,serial,generation,capability) { replaced ->
       if(replaced)result.success(null) else result.error("capture_session_invalid","共享会话已改变，未恢复旧会话",null)
      }
     } else result.error("capture_session_invalid","共享会话已改变，未恢复旧会话",null)
    }
    "usbWindow" -> {
     val session=call.argument<String>("usbSession")
     val body=call.argument<String>("body")
     if(session==null || body==null || body.length>1024 || !UsbLaunchBridge.matches(session)) {
      result.error("usb_invalid","USB窗口会话无效",null)
     } else {
      try {
       ScreenShareService.usbWindow(session,org.json.JSONObject(body)) { response ->
        if(response!=null)result.success(response) else result.error("usb_window_failed","USB窗口握手失败",null)
       }
      } catch(_: Exception) { result.error("usb_invalid","USB窗口请求无效",null) }
     }
    }
    "renewUsbCapture" -> {
     val session=call.argument<String>("usbSession")
     val device=call.argument<String>("device")
     val serial=call.argument<String>("serial")
     val challenge=call.argument<String>("challenge")
     val proof=call.argument<String>("proof")
     if(session==null || !UsbLaunchBridge.matches(session) || serial!=UsbLaunchBridge.serialFor(session) || device==null ||
       challenge==null || proof==null || !Regex("[0-9a-fA-F]{64}").matches(challenge) || !Regex("[0-9a-fA-F]{64}").matches(proof)) {
      result.error("usb_invalid","USB续期身份无效",null)
     } else {
      val body=org.json.JSONObject().put("device",device).put("serial",serial).put("challenge",challenge).put("proof",proof)
      ScreenShareService.renewUsbCapture(body,session) { renewed ->
       if(renewed)result.success(null) else result.error("capture_renew_failed","USB共享续期未完成",null)
      }
     }
    }
    "renewCapture" -> {
     val controlTicket=call.argument<String>("controlTicket")
     val session=call.argument<String>("usbSession")
     if(controlTicket==null || session==null || !Regex("[A-Za-z0-9_-]{43}").matches(controlTicket) ||
        !ScreenShareService.active || ScreenShareService.usbOwnerSession!=session || !UsbLaunchBridge.matches(session)) {
      result.error("capture_session_invalid","屏幕共享会话已失效",null)
     } else {
      ScreenShareService.renewCapture(controlTicket,session) { renewed ->
       if(renewed)result.success(null) else result.error("capture_renew_failed","共享授权续期未完成",null)
      }
     }
    }
    "status" -> result.success(org.json.JSONObject().put("capture",ScreenShareService.status).put("task",ScreenShareService.taskStatus).put("active",ScreenShareService.active).toString())
    else -> result.notImplemented()
   }
  }
  // 悬浮状态条（pill）：Flutter 计算状态，原生只负责窗口与手势。
  val pill = MethodChannel(engine.dartExecutor.binaryMessenger,"pcflash/pill")
  OverlayPill.setNotifier(pill)
  pill.setMethodCallHandler { call,result ->
   when(call.method) {
    "canShow" -> result.success(OverlayPill.canShow(this))
    "openSettings" -> if(OverlayPill.openSettings(this))result.success(null) else result.error("settings_unavailable","无法打开悬浮窗权限设置，请从系统设置 → 应用 → 显示在其他应用上层 手动开启",null)
    "battery" -> result.success(OverlayPill.battery(this))
    "show" -> if(OverlayPill.show(this,call.arguments as? Map<*,*> ?: emptyMap<Any,Any>()))result.success(null) else result.error("overlay_unavailable","无法显示悬浮状态条，请确认已授予悬浮窗权限",null)
    "update" -> result.success(OverlayPill.update(this,call.arguments as? Map<*,*> ?: emptyMap<Any,Any>()))
    "hide" -> {OverlayPill.hide();result.success(null)}
    else -> result.notImplemented()
   }
  }
  // vc90 自绘光标：动作分发前红圈=意图坐标、板端回执后绿圈；画进共享帧供引擎 OCR 核验落点。
  val cursor = MethodChannel(engine.dartExecutor.binaryMessenger,"pcflash/cursor")
  cursor.setMethodCallHandler { call,result ->
   when(call.method) {
    "canShow" -> result.success(CursorMarker.canShow(this))
    "intent" -> {
     CursorMarker.intent(this,
      (call.argument<Number>("x") ?: 0).toDouble(),(call.argument<Number>("y") ?: 0).toDouble(),
      call.argument<Number>("frameW")?.toDouble(),call.argument<Number>("frameH")?.toDouble())
     result.success(null)
    }
    "ack" -> {
     CursorMarker.ack(this,
      (call.argument<Number>("x") ?: 0).toDouble(),(call.argument<Number>("y") ?: 0).toDouble(),
      call.argument<Number>("frameW")?.toDouble(),call.argument<Number>("frameH")?.toDouble())
     result.success(null)
    }
    else -> result.notImplemented()
   }
  }
 }
 override fun onDestroy() {
  imeRemoteToken?.let { RelayInputOwner.endRemote(it) }; imeRemoteToken = null
  billTextLoop.close()
  usbProof?.close();usbProof=null
  UsbLaunchBridge.detachOwner(this)
  // Flutter 引擎随 Activity 一起销毁，pill 不再刷新；必须摘掉窗口避免残留。
  OverlayPill.hide();OverlayPill.setNotifier(null)
  CursorMarker.remove()
  ticket?.let { ScreenShareService.revoke(it) };ticket=null
  pending?.error("cancelled","共享授权已中断，请重新开启",null);pending=null
  super.onDestroy()
 }
 @Deprecated("Activity result is required for projection consent")
 override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
  super.onActivityResult(requestCode,resultCode,data)
  if(requestCode!=pendingRequestCode)return
  pendingRequestCode=-1;consentInFlight=false
  val requestedUsb=pendingUsbSession;pendingUsbSession=null
  val reply=pending;pending=null
  val capability=ticket;ticket=null
  if(resultCode!=Activity.RESULT_OK || data==null || capability==null || (requestedUsb!=null && !UsbLaunchBridge.matches(requestedUsb))) {
   capability?.let { ScreenShareService.revoke(it) };reply?.error("cancelled","未同意屏幕共享",null);return
  }
  val intent=Intent(this,ScreenShareService::class.java).putExtra("grant",data).putExtra("ticket",capability).putExtra("usbSession",requestedUsb)
  try {
   if(Build.VERSION.SDK_INT>=26)startForegroundService(intent) else startService(intent)
   reply?.success(null)
  } catch(e: Exception) { ScreenShareService.revoke(capability);reply?.error("start_failed","无法启动屏幕共享",null) }
 }
    // vc91: auto-enable network/wired adb on app start (WRITE_SECURE_SETTINGS is granted).
    // HyperOS kills wireless debugging on wifi changes; this brings it back whenever the
    // controller app is opened so the ops-side adb channel recovers by itself.
    // vc93: HyperOS ignores the settings write alone (listener never starts), so we also
    // self-enable our accessibility guide service and, when wireless debugging is truly
    // off and no screen-share is running, auto-open the dev settings page where the a11y
    // state machine flips the toggle and captures the pairing code for the user.
    private fun ensureAdbAutoEnable() {
        try {
            val cr = applicationContext.contentResolver
            Settings.Global.putInt(cr, "adb_wifi_enabled", 1)
            Settings.Global.putInt(cr, "adb_enabled", 1)
        } catch (t: Throwable) {
            android.util.Log.w("vc91-adb", "adb auto-enable failed: ${t.message}")
        }
        try {
            val cr = applicationContext.contentResolver
            val own = "$packageName/org.example.phonecontroller.AccessibilityAssistService"
            val existing = Settings.Secure.getString(cr, "enabled_accessibility_services") ?: ""
            val parts = existing.split(":").map { it.trim() }.filter { it.isNotEmpty() }
            if (own !in parts) {
                Settings.Secure.putString(
                    cr,
                    "enabled_accessibility_services",
                    (parts + own).joinToString(":")
                )
            }
            Settings.Secure.putInt(cr, "accessibility_enabled", 1)
        } catch (t: Throwable) {
            android.util.Log.w("vc93-a11y", "a11y auto-enable failed: ${t.message}")
        }
        // Delayed auto-guide: only when wireless debugging is truly off AND no screen
        // share (grinding) is active. 8s delay lets an automated relaunch (watchdog
        // tap on the role card) reach controlled mode first and cancel the guide.
        android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({
            try {
                if (ScreenShareService.active) return@postDelayed
                val cachedPort = guidePrefs().getString("main_port", "") ?: ""
                if (wirelessDebugPort().isNotEmpty() || probePort(cachedPort)) return@postDelayed
                if (System.currentTimeMillis() - guidePrefs().getLong("last_auto_guide", 0L) < 10 * 60 * 1000L) return@postDelayed
                guidePrefs().edit().putLong("last_auto_guide", System.currentTimeMillis()).apply()
                AccessibilityAssistService.guideArm(applicationContext, auto = true)
            } catch (t: Throwable) {
                android.util.Log.w("vc93-guide", "auto guide failed: ${t.message}")
            }
        }, 8000L)
    }

    private fun guidePrefs() = getSharedPreferences("adb-guide", MODE_PRIVATE)

    // HyperOS never fills service.adb.tls.port even with the listener up, so the
    // reliable liveness check is a direct TCP probe of the cached connect port.
    private fun probePort(port: String): Boolean {
        val p = port.substringAfterLast(':').toIntOrNull() ?: return false
        return try {
            java.net.Socket().use { s ->
                s.connect(java.net.InetSocketAddress("127.0.0.1", p), 400)
                true
            }
        } catch (t: Throwable) { false }
    }

    // The wireless debugging listener exposes its tls port via system property; the
    // property is readable through getprop without any hidden API.
    private fun wirelessDebugPort(): String = try {
        val p = Runtime.getRuntime().exec(arrayOf("getprop", "service.adb.tls.port"))
        val out = p.inputStream.bufferedReader().readLine()?.trim() ?: ""
        p.waitFor()
        out
    } catch (t: Throwable) { "" }

}
