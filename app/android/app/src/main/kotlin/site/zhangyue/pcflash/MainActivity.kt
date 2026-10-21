package site.zhangyue.pcflash

import android.app.Activity
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.os.Build
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity: FlutterActivity() {
 private var pending: MethodChannel.Result? = null
 private var ticket: String? = null
 override fun configureFlutterEngine(engine: FlutterEngine) {
  super.configureFlutterEngine(engine)
  MethodChannel(engine.dartExecutor.binaryMessenger, "pcflash/screen").setMethodCallHandler { call, result ->
   when(call.method) {
    "start" -> {
     val value=call.argument<String>("ticket")
     if(pending!=null || value==null || !Regex("[A-Za-z0-9_-]{43}").matches(value)) {
      result.error("busy", "共享正在准备或凭证无效", null)
     } else {
      pending=result;ticket=value
      val manager=getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
      startActivityForResult(manager.createScreenCaptureIntent(), 901)
     }
    }
    "stop" -> { stopService(Intent(this, ScreenShareService::class.java));result.success(null) }
    "status" -> result.success(ScreenShareService.status)
    else -> result.notImplemented()
   }
  }
 }
 @Deprecated("Activity result is required for projection consent")
 override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
  super.onActivityResult(requestCode,resultCode,data)
  if(requestCode!=901)return
  val reply=pending;pending=null
  val capability=ticket;ticket=null
  if(resultCode!=Activity.RESULT_OK || data==null || capability==null) {
   reply?.error("cancelled","未同意屏幕共享",null);return
  }
  val intent=Intent(this,ScreenShareService::class.java).putExtra("grant",data).putExtra("ticket",capability)
  try {
   if(Build.VERSION.SDK_INT>=26)startForegroundService(intent) else startService(intent)
   reply?.success(null)
  } catch(e: Exception) { reply?.error("start_failed","无法启动屏幕共享",null) }
 }
}
