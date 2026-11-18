package org.example.phonecontroller

import android.accessibilityservice.AccessibilityService
import android.content.Context
import android.graphics.Rect
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.provider.Settings
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

/** Optional passive observations only. No screenshot or input API is exposed. */
class AccessibilityAssistService : AccessibilityService() {
 companion object {
  @Volatile private var instance: AccessibilityAssistService?=null
  private val packages=setOf("com.eg.android.AlipayGphone","com.tencent.mm","com.sankuai.meituan","com.xunmeng.pinduoduo","com.android.miaoa.achai","com.miui.home","com.android.launcher","com.android.launcher3","com.google.android.apps.nexuslauncher","com.hihonor.android.launcher","com.huawei.android.launcher")
  fun enabled(context: Context)=context.getSharedPreferences("accessibility-assist",Context.MODE_PRIVATE).getBoolean("enabled",false)
  fun status(context: Context): Map<String,Any> = mapOf("supported" to true,"enabled" to enabled(context),"connected" to (instance!=null),"captureActive" to ScreenShareService.active)
  fun setEnabled(context: Context,value: Boolean): Boolean=context.getSharedPreferences("accessibility-assist",Context.MODE_PRIVATE).edit().putBoolean("enabled",value).commit()
  fun settingsIntent(): android.content.Intent = android.content.Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)
  fun epoch(): Long=instance?.generation ?: -1L
  fun snapshot(frameNanos: Long,width: Int,height: Int,epoch: Long): JSONObject? {
   val service=instance ?: return null
   if(!ScreenShareService.active || !enabled(service))return null
   val result=AtomicReference<JSONObject?>();val latch=CountDownLatch(1)
   val action=Runnable { try {result.set(service.readTree(frameNanos,width,height,epoch))} catch(_: Exception) {} finally {latch.countDown()} }
   if(Looper.myLooper()==Looper.getMainLooper())action.run() else {
    service.main.post(action)
    if(!latch.await(120,TimeUnit.MILLISECONDS)){service.main.removeCallbacks(action);return null}
   }
   return if(instance===service && ScreenShareService.active && enabled(service))result.get() else null
  }
 }
 private val main=Handler(Looper.getMainLooper())
 @Volatile private var generation=0L
 private var changedNanos=System.nanoTime()
 override fun onServiceConnected(){instance=this;generation++;changedNanos=System.nanoTime()}
 override fun onAccessibilityEvent(event: AccessibilityEvent?){generation++;changedNanos=System.nanoTime()}
 override fun onInterrupt(){generation++;changedNanos=System.nanoTime()}
 override fun onUnbind(intent: android.content.Intent?): Boolean {if(instance===this)instance=null;generation++;return super.onUnbind(intent)}
 override fun onDestroy(){if(instance===this)instance=null;generation++;super.onDestroy()}
 @Suppress("DEPRECATION")
 private fun readTree(frameNanos: Long,width: Int,height: Int,epoch: Long): JSONObject? {
  if(instance!==this || !ScreenShareService.active || !enabled(this))return null
  val now=System.nanoTime();val quiet=(now-changedNanos)/1000000L;val before=generation
  if(epoch!=before || changedNanos>frameNanos || !AccessibilityFrameGuard.accept(frameNanos,now,before,generation,quiet) || width<=0 || height<=0)return null
  val root=rootInActiveWindow ?: return null
  try {
   val pkg=root.packageName?.toString() ?: return null
   if(pkg !in packages)return null
   val nodes=JSONArray();val path=HashSet<AccessibilityNodeInfo>();var visited=0;var complete=true
   val deadline=SystemClock.uptimeMillis()+60
   fun visit(node: AccessibilityNodeInfo,depth: Int,parentClickable: Boolean) {
    if(!complete)return
    if(depth>40 || ++visited>1200 || SystemClock.uptimeMillis()>deadline){complete=false;return}
    if(!path.add(node)){complete=false;return}
    try {
     if(node.isPassword || !node.isVisibleToUser)return
     if(node.packageName?.toString()!=pkg)return
     val rect=Rect();node.getBoundsInScreen(rect)
     val visible=rect.intersect(0,0,width,height)
     if(!visible)return
     val clickable=node.isEnabled && (node.isClickable || parentClickable)
     val text=node.text?.toString()?.take(160) ?: ""
     val description=node.contentDescription?.toString()?.take(160) ?: ""
     if(text.isNotBlank() || description.isNotBlank()) {
      if(nodes.length()>=192){complete=false;return}
      nodes.put(JSONObject().put("text",text).put("description",description).put("bounds",JSONArray(listOf(rect.left,rect.top,rect.right,rect.bottom))).put("clickable",clickable).put("editable",node.isEditable))
     }
     val count=node.childCount
     if(count>1200){complete=false;return}
     for(i in 0 until count){
      val child=node.getChild(i) ?: continue
      if(child===node){complete=false;break}
      try {visit(child,depth+1,clickable)} finally {if(child !in path)child.recycle()}
      if(!complete)break
     }
    } finally {path.remove(node)}
   }
   visit(root,0,false)
   val end=System.nanoTime()
   if(!complete || nodes.length()==0 || !AccessibilityFrameGuard.accept(frameNanos,end,before,generation,(end-changedNanos)/1000000L))return null
   val result=JSONObject().put("version",1).put("width",width).put("height",height).put("package",pkg).put("ageMs",(end-frameNanos)/1000000L).put("stableForMs",minOf(3600000L,(end-changedNanos)/1000000L)).put("nodes",nodes)
   return if(result.toString().toByteArray(Charsets.UTF_8).size<=65536)result else null
  } finally {root.recycle()}
 }
}
