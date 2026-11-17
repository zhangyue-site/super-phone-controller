package org.example.phonecontroller

import org.json.JSONArray
import org.json.JSONObject
import java.nio.ByteBuffer
import java.security.MessageDigest
import kotlin.math.abs

/** Read-only local facts; never sends input or grants control permission. */
class LocalObservationBridge {
 private val tracker=LocalRegionStability().also{it.traceRole("agent_target")}
 private var scope=""
 private var width=0
 private var height=0
 private var nextId=1L
 private var ocrTargets=emptyList<LocalRegionStability.Target>()
 private var external: JSONObject?=null
 private var latestHints=JSONArray()
 private fun digest(text: String)=MessageDigest.getInstance("SHA-256").digest(text.toByteArray(Charsets.UTF_8)).joinToString(""){"%02x".format(it)}
 // Diagnostics only: fixed reasons and counts for one requested target at a time.
 // No screen text, label, bounds or request id leaves this class through them.
 private var watchedId=""
 private var watchedAt=0L
 private var declinedNote=""
 private var reportsSent=0
 private var reportsReady=0
 private var reportsDropped=0
 private fun requestId(value: JSONObject?)=value?.optJSONArray("regions")?.optJSONObject(0)?.optString("id")?:""
 private fun watch(id: String,endReason: String){
  if(id==watchedId)return
  val trace=tracker.drainTrace()
  if(watchedId.isNotEmpty())SafeDiagnostics.record(mapOf("event" to "local_stability","phase" to "frame","reason" to endReason,
   "observed_frames" to trace.frames,"rejected_frames" to trace.rejected,"gap_resets" to trace.gapResets,"change_resets" to trace.changeResets,
   "max_gap_ms" to trace.maxGapMs,"best_count" to trace.bestCount,"best_stable_ms" to trace.bestStableMs,"ready" to trace.ready,
   "reports_sent" to reportsSent,"reports_ready" to reportsReady,"reports_dropped" to reportsDropped,
   "watch_ms" to (System.nanoTime()-watchedAt)/1_000_000L))
  watchedId=id;watchedAt=System.nanoTime();reportsSent=0;reportsReady=0;reportsDropped=0
  if(id.isNotEmpty())SafeDiagnostics.record(mapOf("event" to "local_stability","phase" to "frame","reason" to "request_begin",
   "burst_enabled" to BuildConfig.SOURCE_BURST_EXPERIMENT))
 }
 /** One row per request the phone saw but did not adopt; changes nothing else. */
 @Synchronized fun declined(value: JSONObject,reason: String){
  val note=requestId(value)+":"+reason
  if(note==declinedNote)return
  declinedNote=note
  SafeDiagnostics.record(mapOf("event" to "local_stability","phase" to "status","reason" to reason))
 }
 @Synchronized fun clear(){watch("","watch_cleared");tracker.clear();scope="";width=0;height=0;nextId=1;ocrTargets=emptyList();external=null;latestHints=JSONArray()}
 private fun ensureScope(value: String,w: Int,h: Int){
  if(scope!=value || width!=w || height!=h){clear();scope=value;width=w;height=h;tracker.configure(value,w,h,emptyList())}
 }
 private fun targets(): List<LocalRegionStability.Target> {
  val result=mutableListOf<LocalRegionStability.Target>()
  external?.optJSONArray("regions")?.let { rows ->
   for(i in 0 until minOf(rows.length(),4)){
    val r=rows.optJSONObject(i)?:continue;val b=r.optJSONArray("bounds")?:continue
    if(b.length()!=4)continue
    val id=r.optString("id");val label=r.optString("label")
    val values=(0..3).map{b.optInt(it,-1)}
    if(!Regex("[A-Za-z0-9:_-]{1,96}").matches(id) || label.isEmpty() || label.length>160 || values[0]<0 || values[1]<0 || values[0]>=values[2] || values[1]>=values[3] || values[2]>width || values[3]>height)continue
    result.add(LocalRegionStability.Target(id,label,"agent_target",values[0],values[1],values[2],values[3]))
   }
  }
  result.addAll(ocrTargets.take(64-result.size));return result
 }
 @Synchronized fun request(value: JSONObject?,currentScope: String,w: Int,h: Int,barrier: String){
  ensureScope(currentScope,w,h)
  external=if(value!=null && value.optString("barrier")==barrier && value.optInt("width")==w && value.optInt("height")==h && value.optInt("requiredFrames")==10)value else null
  tracker.configure(scope,width,height,targets())
  val adopted=external!=null && targets().any{it.role=="agent_target"}
  if(value!=null && !adopted)declined(value,when{
   value.optString("barrier")!=barrier->"request_barrier_mismatch"
   value.optInt("width")!=w || value.optInt("height")!=h->"request_geometry_mismatch"
   value.optInt("requiredFrames")!=10->"request_frames_mismatch"
   else->"request_region_invalid"
  })
  watch(if(adopted)requestId(external) else "","request_end")
 }
 @Synchronized fun wantsFastSamples(currentScope: String): Boolean = scope==currentScope && external!=null
 // Only a validated external target set can request a bounded source burst.
 @Synchronized fun burstRequestKey(currentScope: String): String? {
  if(scope!=currentScope || external==null)return null
  val requested=targets().filter{it.role=="agent_target"}
  if(requested.isEmpty())return null
  return digest(currentScope+requested.joinToString(";"){"${it.id}:${it.label}:${it.left},${it.top},${it.right},${it.bottom}"})
 }
 @Synchronized fun burstReady(currentScope: String,capturedAt: Long): Boolean {
  if(burstRequestKey(currentScope)==null)return false
  val snapshot=tracker.snapshotAt(capturedAt) ?: return false
  if(!snapshot.valid || snapshot.scope!=currentScope || snapshot.sourceTimestampNs!=capturedAt ||
    System.nanoTime()-capturedAt !in 0L..250_000_000L)return false
  val ids=targets().filter{it.role=="agent_target"}.map{it.id}
  return ids.isNotEmpty() && ids.all{id->snapshot.regions.any{it.id==id && it.ready}}
 }
 @Synchronized fun sample(value: String,seq: Long,capturedAt: Long,pixels: ByteBuffer,sourceW: Int,sourceH: Int,pixelStride: Int,rowStride: Int,w: Int,h: Int){
  ensureScope(value,w,h)
  tracker.observe(value,seq,capturedAt,pixels,sourceW,sourceH,pixelStride,rowStride)
 }
 private fun role(label: String): String = when {
  label.contains("跳过") && !label.contains("片头") && !label.contains("片尾") -> "ad_skip_candidate"
  label.trim() in setOf("关闭","关闭广告","×","X","x","✕") -> "ad_close_candidate"
  else -> "text_candidate"
 }
 private fun updateOcr(ocr: JSONObject){
  val rows=ocr.optJSONArray("lines")?:return
  val next=mutableListOf<LocalRegionStability.Target>();val used=mutableSetOf<String>();val hints=JSONArray()
  for(i in 0 until minOf(rows.length(),64)){
   val r=rows.optJSONObject(i)?:continue;val b=r.optJSONArray("bounds")?:continue
   val label=r.optString("text");if(label.isEmpty() || label.length>160 || b.length()!=4)continue
   val v=(0..3).map{b.optInt(it,-1)}
   if(v[0]<0 || v[1]<0 || v[0]>=v[2] || v[1]>=v[3] || v[2]>width || v[3]>height)continue
   val kind=role(label)
   val previous=ocrTargets.firstOrNull{it.id !in used && it.label==label && it.role==kind && maxOf(abs(it.left-v[0]),abs(it.top-v[1]),abs(it.right-v[2]),abs(it.bottom-v[3]))<=3}
   val id=previous?.id?:"ocr-${nextId++}"
   used.add(id);next.add(LocalRegionStability.Target(id,label,kind,v[0],v[1],v[2],v[3]))
   val hint=when {
    kind!="text_candidate"->kind
    label.trim()=="广告"->"ad_marker"
    Regex("隐私政策|用户协议|是否允许|确认协议并支付|立即支付|授权登录").containsMatchIn(label)->"protected_surface"
    else->null
   }
   if(hint!=null && hints.length()<16)hints.put(JSONObject().put("kind",hint).put("label",label).put("bounds",JSONArray(v)))
  }
  ocrTargets=next;latestHints=hints;tracker.configure(scope,width,height,targets())
 }
 @Synchronized fun report(ocr: JSONObject,capturedAt: Long,currentScope: String): JSONObject? {
  if(scope!=currentScope || width!=ocr.optInt("width") || height!=ocr.optInt("height")){
   if(watchedId.isNotEmpty())reportsDropped++
   return null
  }
  // Snapshot lookup precedes OCR configuration: no future count is put on an old JPEG.
  val snapshot=tracker.snapshotAt(capturedAt)
  updateOcr(ocr)
  val age=(System.nanoTime()-capturedAt)/1_000_000L
  val output=if(snapshot!=null && snapshot.valid && snapshot.scope==currentScope && snapshot.sourceTimestampNs==capturedAt && age in 0..2500){
   val regions=JSONArray()
   for(r in snapshot.regions){
    regions.put(JSONObject().put("id",r.id).put("label",r.label).put("role",r.role).put("bounds",JSONArray(listOf(r.left,r.top,r.right,r.bottom))).put("count",r.count).put("stableMs",r.stableMs).put("ready",r.ready))
   }
   JSONObject().put("v",1).put("scopeHash",digest(currentScope)).put("sourceSequence",snapshot.sourceSeq).put("sourceTimestampNs",snapshot.sourceTimestampNs).put("sourceWidth",snapshot.sourceWidth).put("sourceHeight",snapshot.sourceHeight).put("ageMs",age).put("requiredFrames",10).put("minStableMs",600).put("regions",regions).put("layoutHints",JSONArray(latestHints.toString()))
  } else null
  if(watchedId.isNotEmpty()){
   if(output==null)reportsDropped++
   else{
    reportsSent++
    if(snapshot?.regions?.any{it.id==watchedId && it.ready}==true)reportsReady++
   }
  }
  return output
 }
}
