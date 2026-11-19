package org.example.phonecontroller

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.PixelFormat
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.view.WindowManager

/**
 * 自绘光标标记层（vc90 反馈闭环）。
 *
 * 控制板回执只代表板端写入成功，不代表动作在画面上的真实落点；引擎从
 * 共享帧里看不到自己的意图位置。这里用系统悬浮窗（复用已有的
 * SYSTEM_ALERT_WINDOW 权限）在动作坐标画一个共享帧可见的圆环：
 * 分发前红圈=意图坐标（最长 2 秒），收到板端回执后变绿圈（再留 1 秒）。
 * MediaProjection 共享帧会捕获悬浮窗，引擎 OCR 因此能从帧里核验落点。
 *
 * 坐标换算：动作坐标来自共享帧空间；传入 frameW/frameH 时按当前真实
 * 屏幕尺寸（实机 1200x2608）等比换算，缺省视为已是实机像素并做边界钳制。
 * 无悬浮窗权限时静默跳过，不影响控制链路。
 */
object CursorMarker {
 private const val RED_MS=2000L
 private const val GREEN_MS=1000L
 private const val RADIUS_DIP=20f
 private const val RING_DIP=5f
 private const val DOT_DIP=6f
 private val ui=Handler(Looper.getMainLooper())
 private var view: MarkerView?=null
 private var port: AndroidOverlayWindowPort?=null
 private var manager: WindowManager?=null
 private val removeRun=Runnable { remove() }

 fun canShow(context: Context): Boolean = Settings.canDrawOverlays(context)

 /** 动作分发：在意图坐标画红圈（意图标记），最多显示 RED_MS。 */
 @Synchronized
 fun intent(context: Context,x: Double,y: Double,frameW: Double?,frameH: Double?) {
  if(!canShow(context))return
  if(show(context,x,y,frameW,frameH,Color.rgb(229,57,53)))
   ui.postDelayed(removeRun,RED_MS)
 }

 /** 板端回执：变绿圈（已执行标记），GREEN_MS 后移除。 */
 @Synchronized
 fun ack(context: Context,x: Double,y: Double,frameW: Double?,frameH: Double?) {
  if(!canShow(context))return
  ui.removeCallbacks(removeRun)
  if(view!=null) {
   view?.color=Color.rgb(67,160,71);view?.invalidate()
   ui.postDelayed(removeRun,GREEN_MS)
  } else if(show(context,x,y,frameW,frameH,Color.rgb(67,160,71))) {
   // 回执先于悬浮窗建立（极快回执）：补画绿圈，保证闭环可见。
   ui.postDelayed(removeRun,GREEN_MS)
  }
 }

 @Synchronized
 fun remove() {
  ui.removeCallbacks(removeRun)
  port?.remove();port=null
  view=null;manager=null
 }

 /** 建窗或复用旧窗，移动到新坐标并着色。返回是否成功显示。 */
 private fun show(context: Context,x: Double,y: Double,frameW: Double?,frameH: Double?,color: Int): Boolean {
  val app=context.applicationContext
  val real=realDisplaySize(app)
  var px=x;var py=y
  if(frameW!=null && frameH!=null && frameW>0 && frameH>0) { px=x*real.first/frameW;py=y*real.second/frameH }
  px=px.coerceIn(0.0,(real.first-1).toDouble());py=py.coerceIn(0.0,(real.second-1).toDouble())
  try {
   val wm=(manager ?: (app.getSystemService(Context.WINDOW_SERVICE) as WindowManager).also{manager=it})
   val density=app.resources.displayMetrics.density
   val radius=(RADIUS_DIP*density).toInt();val ring=(RING_DIP*density).toInt()
   if(view==null || port==null) {
    remove()
    manager=wm
    val v=MarkerView(app,radius,ring,color)
    val params=WindowManager.LayoutParams(radius*2,radius*2,
     WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
     WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
      WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
      WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
     PixelFormat.TRANSLUCENT)
    params.gravity=Gravity.TOP or Gravity.START
    params.x=px.toInt()-radius;params.y=py.toInt()-radius
    val p=AndroidOverlayWindowPort(wm,v,params)
    p.add()
    port=p;view=v
   } else {
    port?.update(px.toInt()-radius,py.toInt()-radius)
    view?.color=color;view?.invalidate()
   }
   return true
  } catch(e: Exception) {
   // 悬浮窗被系统回收等场景：静默降级，不影响控制链路。
   SafeDiagnostics.record(mapOf("event" to "cursor_overlay_failed","phase" to "cursor","reason" to (e.message?:"overlay")))
   remove()
   return false
  }
 }

 private fun realDisplaySize(context: Context): Pair<Int,Int> {
  val wm=context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
  return try {
   if(Build.VERSION.SDK_INT>=30) {
    val b=wm.currentWindowMetrics.bounds;Pair(b.width(),b.height())
   } else {
    @Suppress("DEPRECATION") val size=android.graphics.Point()
    @Suppress("DEPRECATION") wm.defaultDisplay.getRealSize(size);Pair(size.x,size.y)
   }
  } catch(_: Exception) { Pair(1200,2608) }
 }

 /** 圆环 + 中心点；color 可切换红/绿。 */
 private class MarkerView(context: Context,val radiusPx: Int,val ringPx: Int,var color: Int) : View(context) {
  private val ring=Paint(Paint.ANTI_ALIAS_FLAG).apply{style=Paint.Style.STROKE}
  private val dot=Paint(Paint.ANTI_ALIAS_FLAG).apply{style=Paint.Style.FILL}
  override fun onDraw(canvas: Canvas) {
   val c=radiusPx.toFloat()
   ring.color=color;ring.strokeWidth=ringPx.toFloat()
   dot.color=color
   canvas.drawCircle(c,c,c-ringPx/2f,ring)
   canvas.drawCircle(c,c,DOT_DIP*resources.displayMetrics.density,dot)
  }
 }
}
