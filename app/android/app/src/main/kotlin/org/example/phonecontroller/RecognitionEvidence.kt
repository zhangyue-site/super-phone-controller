package org.example.phonecontroller

import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/** Read-only metadata, no screen text or transaction fields in this envelope. */
object RecognitionEvidence {
 private var id=""
 private var kind=""
 private var epoch=0L
 private var afterFrame=0L
 private var state="idle"
 private var preview=""
 private var received=0
 private var receivedDone=false
 private val rows=mutableListOf<JSONObject>()
 @Synchronized fun begin(source: String,captureEpoch: Long): String {
  id=UUID.randomUUID().toString().replace("-","")
  kind=source;epoch=captureEpoch;afterFrame=System.nanoTime();state="running";received=0;receivedDone=false;preview="";rows.clear()
  return id
 }
 @Synchronized fun matches(run: String)=id==run && state=="running"
 @Synchronized fun source()=kind
 @Synchronized fun frame(run: String,frame: LoopFrame,age: Long,ms: Int,lines: Int,page: String): Boolean {
  if(!matches(run)||frame.captureEpoch!=epoch||frame.capturedAt<=afterFrame||rows.size>=10||
    rows.any{it.optString("frame")==frame.capturedAt.toString()})return false
  rows.add(JSONObject().put("frame",frame.capturedAt.toString()).put("age",age.coerceIn(0,2500))
   .put("ms",ms.coerceIn(0,60000)).put("lines",lines.coerceIn(0,60000))
   .put("width",frame.width).put("height",frame.height).put("page",page))
  return true
 }
 @Synchronized fun preview(run: String,text: String){if(matches(run))preview=text.lineSequence().take(6).joinToString("\n").take(300)}
 @Synchronized fun finish(run: String,reason: String){if(id==run && state=="running")state=reason}
 @Synchronized fun envelope(): String? {
  if(id.isEmpty())return null
  return JSONObject().put("v",1).put("run",id).put("source",kind).put("epoch",epoch.toString())
   .put("state",state).put("frames",JSONArray(rows)).toString()
 }
 @Synchronized fun acknowledge(value: JSONObject?) {
  if(value==null||value.optString("run")!=id)return
  val n=value.optInt("count",-1)
  if(n in received..rows.size){received=n;receivedDone=value.optString("state")=="done" && n==10}
 }
 @Synchronized fun status(): Map<String,Any> = mapOf("run" to id,"source" to kind,
  "active" to (state=="running"),"state" to state,"count" to rows.size,
  "received" to received,"receivedDone" to receivedDone,"preview" to preview)
}
