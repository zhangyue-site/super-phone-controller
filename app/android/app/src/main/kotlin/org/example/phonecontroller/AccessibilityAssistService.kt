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
 fun setText(context: Context,text: String): Boolean {
  val service=instance ?: return false
  if(text.isEmpty())return false
  return service.runCatching{setEditableText(text)}.getOrDefault(false)
 }
 fun clickLabel(context: Context,label: String): Boolean {
  val service=instance ?: return false
  if(label.isEmpty())return false
  return service.runCatching{clickByLabel(label)}.getOrDefault(false)
 }
 // vc93: auto-guide for wireless debugging. Arms a state machine that follows the
 // Settings UI: dev options -> wireless debugging page -> flip toggle -> pairing
 // dialog -> capture pairing code + port into prefs for the in-app card.
 fun guideArm(context: Context, auto: Boolean) {
  val prefs=context.getSharedPreferences("adb-guide",Context.MODE_PRIVATE)
  prefs.edit().putBoolean("armed",true).putInt("step",1).putLong("armed_at",System.currentTimeMillis())
    .putBoolean("auto",auto).putString("err","").putString("pair_code","").putString("pair_port","").commit()
  try {
   val i=android.content.Intent(android.provider.Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS)
   i.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
   context.startActivity(i)
  } catch (_: Throwable) {}
  instance?.let { it.main.removeCallbacks(it.guideRunnable);it.main.postDelayed(it.guideRunnable,600) }
 }
 fun guideStatus(context: Context): Map<String, Any> {
  val prefs=context.getSharedPreferences("adb-guide",Context.MODE_PRIVATE)
  return mapOf("armed" to prefs.getBoolean("armed",false),
    "step" to prefs.getInt("step",0),
    "pairCode" to (prefs.getString("pair_code","")?:""),
    "pairPort" to (prefs.getString("pair_port","")?:""),
    "err" to (prefs.getString("err","")?:""))
 }
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
 private fun setEditableText(text: String): Boolean {
  val root=rootInActiveWindow ?: return false
  var focused: AccessibilityNodeInfo?=null
  var anyEditable: AccessibilityNodeInfo?=null
  val stack=java.util.ArrayDeque<AccessibilityNodeInfo>();stack.add(root)
  while(stack.isNotEmpty()){
   val n=stack.removeLast()
   if(n.isEditable){
    if(n.isFocused){focused=n;break}
    if(anyEditable==null)anyEditable=n
   }
   for(i in 0 until n.childCount)n.getChild(i)?.let{stack.add(it)}
  }
  val node=focused?:anyEditable?:return false
  node.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
  val args=android.os.Bundle().apply{putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,text)}
  return node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,args)
 }

 private fun clickByLabel(label: String): Boolean {
  val root=rootInActiveWindow ?: return false
  val stack=java.util.ArrayDeque<AccessibilityNodeInfo>();stack.add(root)
  while(stack.isNotEmpty()){
   val n=stack.removeLast()
   val t=n.text?.toString()?:"";val d=n.contentDescription?.toString()?:""
   if((t==label || d==label) && n.isVisibleToUser){
    var cur: AccessibilityNodeInfo?=n
    var hops=0
    while(cur!=null && hops<4){
     if(cur.isClickable)return cur.performAction(AccessibilityNodeInfo.ACTION_CLICK)
     cur=cur.parent;hops++
    }
   }
   for(i in 0 until n.childCount)n.getChild(i)?.let{stack.add(it)}
  }
  return false
 }

 override fun onServiceConnected(){instance=this;generation++;changedNanos=System.nanoTime()}
 override fun onAccessibilityEvent(event: AccessibilityEvent?){
  generation++;changedNanos=System.nanoTime()
  if(guidePrefs().getBoolean("armed",false)){
   main.removeCallbacks(guideRunnable);main.postDelayed(guideRunnable,350)
  }
 }
 private fun guidePrefs()=getSharedPreferences("adb-guide",Context.MODE_PRIVATE)
 private val guideRunnable=Runnable { guideTick() }
 // vc93 guide state machine. Safety: clicks happen ONLY inside com.android.settings.
 private fun guideTick(){
  val prefs=guidePrefs()
  if(!prefs.getBoolean("armed",false))return
  val now=System.currentTimeMillis()
  if(now-prefs.getLong("armed_at",0L)>120_000L){
   prefs.edit().putBoolean("armed",false).putString("err","timeout").apply();return
  }
  val root=rootInActiveWindow
  if(root==null){main.postDelayed(guideRunnable,800);return}
  try{
   val pkg=root.packageName?.toString()?:""
   if(pkg!="com.android.settings"){main.postDelayed(guideRunnable,800);return}
   val texts=ArrayList<String>()
   val switches=ArrayList<AccessibilityNodeInfo>()
   collectGuide(root,texts,switches,0)
   val joined=texts.joinToString("\n")
   val step=prefs.getInt("step",1)
   when{
    // pairing dialog: "与设备配对 / WLAN 配对码 / 418643 / IP 地址和端口 / x.x.x.x:port / 取消"
    joined.contains("WLAN 配对码")||joined.contains("与设备配对") -> {
     val code=Regex("(?<!\\d)\\d{6}(?!\\d)").find(joined)?.value?:""
     val port=Regex("\\d{1,3}(\\.\\d{1,3}){3}:\\d{2,5}").find(joined)?.value?:""
     if(code.isNotEmpty()&&port.isNotEmpty()){
      prefs.edit().putBoolean("armed",false).putInt("step",5).putString("pair_code",code).putString("pair_port",port).apply()
      clickText(root,"取消")
     } else main.postDelayed(guideRunnable,800)
    }
    // wireless debugging page: has device name section + pair rows
    joined.contains("扫描二维码配对设备")||joined.contains("输入配对码配对设备")||joined.contains("使用配对码配对设备") -> {
     val sw=switches.firstOrNull()
     if(sw!=null && !sw.isChecked){
      var cur: AccessibilityNodeInfo?=sw;var hops=0
      while(cur!=null&&hops<4){if(cur.isClickable){cur.performAction(AccessibilityNodeInfo.ACTION_CLICK);break};cur=cur.parent;hops++}
      prefs.edit().putInt("step",3).apply();main.postDelayed(guideRunnable,1200)
     } else {
      // toggle already on; open the pairing-code dialog row
      if(clickTextsContain(root,"配对码配对设备")||clickTextsContain(root,"配对设备")){
       prefs.edit().putInt("step",4).apply();main.postDelayed(guideRunnable,1200)
      } else main.postDelayed(guideRunnable,1500)
     }
    }
    // dev options page: find the wireless debugging row
    joined.contains("无线调试") -> {
     if(clickTextsContain(root,"无线调试")){
      prefs.edit().putInt("step",2).apply();main.postDelayed(guideRunnable,1200)
     } else main.postDelayed(guideRunnable,1500)
    }
    else -> main.postDelayed(guideRunnable,1200)
   }
  } finally {root.recycle()}
 }
 private fun collectGuide(node: AccessibilityNodeInfo,texts: MutableList<String>,switches: MutableList<AccessibilityNodeInfo>,depth:Int){
  if(depth>30||texts.size>200)return
  try{
   if(!node.isVisibleToUser)return
   val t=node.text?.toString()?:""
   if(t.isNotBlank())texts.add(t)
   val cls=node.className?.toString()?:""
   if(cls.endsWith("Switch"))switches.add(node)
   val count=node.childCount
   for(i in 0 until count){
    val c=node.getChild(i)?:continue
    try{collectGuide(c,texts,switches,depth+1)}finally{c.recycle()}
   }
  }catch(_:Exception){}
 }
 private fun clickText(root: AccessibilityNodeInfo,text: String): Boolean{
  val stack=java.util.ArrayDeque<AccessibilityNodeInfo>();stack.add(root)
  while(stack.isNotEmpty()){
   val n=stack.removeLast()
   try{
    if(n.isVisibleToUser&&(n.text?.toString()?:"")==text){
     var cur:AccessibilityNodeInfo?=n;var hops=0
     while(cur!=null&&hops<4){if(cur.isClickable)return cur.performAction(AccessibilityNodeInfo.ACTION_CLICK);cur=cur.parent;hops++}
    }
    for(i in 0 until n.childCount)n.getChild(i)?.let{stack.add(it)}
   }catch(_:Exception){}
  }
  return false
 }
 private fun clickTextsContain(root: AccessibilityNodeInfo,frag: String): Boolean{
  val stack=java.util.ArrayDeque<AccessibilityNodeInfo>();stack.add(root)
  while(stack.isNotEmpty()){
   val n=stack.removeLast()
   try{
    if(n.isVisibleToUser&&(n.text?.toString()?:"").contains(frag)){
     var cur:AccessibilityNodeInfo?=n;var hops=0
     while(cur!=null&&hops<4){if(cur.isClickable)return cur.performAction(AccessibilityNodeInfo.ACTION_CLICK);cur=cur.parent;hops++}
    }
    for(i in 0 until n.childCount)n.getChild(i)?.let{stack.add(it)}
   }catch(_:Exception){}
  }
  return false
 }
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
