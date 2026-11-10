package org.example.phonecontroller

import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.TimeUnit

/** Bounded local recognition. The legacy diagnostic envelope carries metadata only. */
object RecognitionEvidence {
 private var id=""
 private var kind=""
 private var epoch=0L
 private var afterFrame=0L
 private var state="idle"
 private var preview=""
 private var received=0
 private var receivedDone=false
 private data class LocalResult(val run: String,val stamp: Long,val epoch: Long,
  val source: String,val count: Int,val text: String?,val boxes: Int?,var state: String,var acknowledged: Int)
 private val results=mutableMapOf<String,LocalResult>()
 private val rows=mutableListOf<JSONObject>()
 @Synchronized fun begin(source: String,captureEpoch: Long): String {
  id=UUID.randomUUID().toString().replace("-","")
  results.remove(source);kind=source;epoch=captureEpoch;afterFrame=System.nanoTime();state="running";received=0;receivedDone=false;preview="";rows.clear()
  return id
 }
 @Synchronized fun matches(run: String)=id==run && state=="running"
 @Synchronized fun source()=kind
 @Synchronized fun outcome(run: String): Pair<String,String>?=if(id==run)Pair(kind,state) else null
 @Synchronized fun clearResults(){preview="";results.clear()}
 @Synchronized fun frame(run: String,frame: LoopFrame,age: Long,ms: Int,lines: Int,page: String,text: String?=null,boxes: Int?=null): Boolean {
  if(!matches(run)||frame.captureEpoch!=epoch||frame.capturedAt<=afterFrame||rows.size>=10||
    rows.any{it.optString("frame")==frame.capturedAt.toString()})return false
  rows.add(JSONObject().put("frame",frame.capturedAt.toString()).put("age",age.coerceIn(0,2500))
   .put("ms",ms.coerceIn(0,60000)).put("lines",lines.coerceIn(0,60000))
   .put("width",frame.width).put("height",frame.height).put("page",page))
  if(text!=null || boxes!=null)results[kind]=LocalResult(id,frame.capturedAt,epoch,kind,
   rows.size,text?.lineSequence()?.take(12)?.joinToString("\n")?.take(480),boxes,"running",results[kind]?.acknowledged?:0)
  return true
 }
 @Synchronized fun preview(run: String,text: String){if(matches(run))preview=text.lineSequence().take(6).joinToString("\n").take(300)}
 @Synchronized fun finish(run: String,reason: String){
  if(id!=run || state!="running")return
  state=reason
  if(reason in setOf("stopped","closed","locked","capture_changed"))clearResults()
  else results[kind]?.takeIf{it.run==run}?.state=reason
 }
 @Synchronized fun localResults(captureEpoch: Long): JSONObject {
  val data=JSONArray()
  for(r in results.values) {
   val age=TimeUnit.NANOSECONDS.toMillis(System.nanoTime()-r.stamp)
   if(r.epoch!=captureEpoch || age !in 0..12000)continue
   val row=JSONObject().put("run",r.run).put("frame",r.stamp.toString())
    .put("epoch",r.epoch.toString()).put("source",r.source).put("count",r.count)
    .put("ageMs",age).put("state",r.state)
   if(r.text!=null)row.put("text",r.text)
   if(r.boxes!=null)row.put("boxes",r.boxes)
   data.put(row)
  }
  return JSONObject().put("v",1).put("platform","android").put("results",data)
 }
 @Synchronized fun envelope(): String? {
  if(id.isEmpty())return null
  return JSONObject().put("v",1).put("run",id).put("source",kind).put("epoch",epoch.toString())
   .put("state",state).put("frames",JSONArray(rows)).toString()
 }
 @Synchronized fun acknowledge(value: JSONObject?) {
  if(value==null||value.optString("run")!=id)return
  val n=value.optInt("count",-1)
  if(n in received..rows.size){
   received=n;receivedDone=value.optString("state")=="done" && n==10
   results[kind]?.let{it.acknowledged=maxOf(it.acknowledged,n)}
  }
 }
 @Synchronized fun acknowledgeLocal(values: JSONArray?) {
  if(values==null || values.length()>2)return
  for(i in 0 until values.length()){
   val item=values.optJSONObject(i)?:continue
   val local=results[item.optString("source")]?:continue
   if(item.optString("run")!=local.run || item.optString("epoch")!=local.epoch.toString())continue
   val count=item.optInt("count",-1)
   if(count in local.acknowledged..local.count)local.acknowledged=count
  }
 }
 @Synchronized fun status(): Map<String,Any> {
  val ocr=results["ocr"]
  return mapOf("run" to id,"source" to kind,"active" to (state=="running"),"state" to state,
   "count" to rows.size,"received" to received,"receivedDone" to receivedDone,"preview" to preview,
   "ocrCount" to (ocr?.count?:0),"ocrReceived" to (ocr?.acknowledged?:0),
   "ocrPreview" to (ocr?.text?.lineSequence()?.take(6)?.joinToString("\n")?.take(300)?:""))
 }
}
