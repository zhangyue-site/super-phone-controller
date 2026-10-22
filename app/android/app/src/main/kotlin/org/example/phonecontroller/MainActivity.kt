package org.example.phonecontroller

import android.app.Activity
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.media.projection.MediaProjectionConfig
import android.net.Uri
import android.os.Build
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity: FlutterActivity() {
 private var pending: MethodChannel.Result? = null
 private var ticket: String? = null
 override fun configureFlutterEngine(engine: FlutterEngine) {
  super.configureFlutterEngine(engine)
  MethodChannel(engine.dartExecutor.binaryMessenger, "pcflash/app").setMethodCallHandler { call, result ->
   when(call.method) {
    "info" -> {
     @Suppress("DEPRECATION")
     val info=packageManager.getPackageInfo(packageName,0)
     @Suppress("DEPRECATION")
     val code=if(Build.VERSION.SDK_INT>=28) info.longVersionCode else info.versionCode.toLong()
     result.success(mapOf("versionName" to info.versionName, "versionCode" to code))
    }
    "openDownload" -> {
     try {
      startActivity(Intent(Intent.ACTION_VIEW,Uri.parse("https://downloads.example.invalid/apps/phone-controller-flash/")))
      result.success(null)
     } catch(_: Exception) { result.error("browser_unavailable","无法打开官方下载页",null) }
    }
    else -> result.notImplemented()
   }
  }
  MethodChannel(engine.dartExecutor.binaryMessenger, "pcflash/screen").setMethodCallHandler { call, result ->
   when(call.method) {
    "start" -> {
     val value=call.argument<String>("ticket")
     if(pending!=null || value==null || !Regex("[A-Za-z0-9_-]{43}").matches(value)) {
      result.error("busy", "共享正在准备或凭证无效", null)
     } else {
      pending=result;ticket=value
      val manager=getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
      try {
       val consent = if(Build.VERSION.SDK_INT>=34) manager.createScreenCaptureIntent(MediaProjectionConfig.createConfigForDefaultDisplay()) else manager.createScreenCaptureIntent()
       startActivityForResult(consent, 901)
      } catch(_: Exception) {
       pending=null;ticket=null;ScreenShareService.revoke(value)
       result.error("permission_failed", "无法请求屏幕共享，请重新开启", null)
      }
     }
    }
    "stop" -> { ticket?.let { ScreenShareService.revoke(it) };ticket=null;pending?.error("cancelled","已取消屏幕共享",null);pending=null;ScreenShareService.status="已停止共享";ScreenShareService.taskStatus=""; stopService(Intent(this, ScreenShareService::class.java));result.success(null) }
    "status" -> result.success(org.json.JSONObject().put("capture",ScreenShareService.status).put("task",ScreenShareService.taskStatus).toString())
    else -> result.notImplemented()
   }
  }
 }
 override fun onDestroy() {
  ticket?.let { ScreenShareService.revoke(it) };ticket=null
  pending?.error("cancelled","共享授权已中断，请重新开启",null);pending=null
  super.onDestroy()
 }
 @Deprecated("Activity result is required for projection consent")
 override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
  super.onActivityResult(requestCode,resultCode,data)
  if(requestCode!=901)return
  val reply=pending;pending=null
  val capability=ticket;ticket=null
  if(resultCode!=Activity.RESULT_OK || data==null || capability==null) {
   capability?.let { ScreenShareService.revoke(it) };reply?.error("cancelled","未同意屏幕共享",null);return
  }
  val intent=Intent(this,ScreenShareService::class.java).putExtra("grant",data).putExtra("ticket",capability)
  try {
   if(Build.VERSION.SDK_INT>=26)startForegroundService(intent) else startService(intent)
   reply?.success(null)
  } catch(e: Exception) { ScreenShareService.revoke(capability);reply?.error("start_failed","无法启动屏幕共享",null) }
 }
}
