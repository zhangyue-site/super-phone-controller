package org.example.phonecontroller

import android.graphics.Bitmap
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.TextRecognizer
import com.google.mlkit.vision.text.chinese.ChineseTextRecognizerOptions
import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest
import java.util.concurrent.Executor
import java.util.concurrent.TimeUnit

/** Local text geometry for the exact uploaded JPEG; never issues phone input. */
class PhoneFrameOcr {
 private val lock=Any()
 private var reader: TextRecognizer?=null
 private var busy=false
 private var closed=false
 fun scan(frame: Bitmap,jpeg: ByteArray,capturedAt: Long): JSONObject? {
  val copy: Bitmap
  val client: TextRecognizer
  synchronized(lock) {
   if(closed||busy)return null
   copy=frame.copy(Bitmap.Config.ARGB_8888,false)?:return null
   client=reader?:TextRecognition.getClient(ChineseTextRecognizerOptions.Builder().build()).also{reader=it}
   busy=true
  }
  var retained=false
  try {
   val task=client.process(InputImage.fromBitmap(copy,0))
   task.addOnCompleteListener(Executor{it.run()}) {
    copy.recycle()
    synchronized(lock){busy=false;if(closed){reader?.close();reader=null}}
   }
   retained=true
   // A timed-out task owns its bitmap until completion; no second task is queued.
   val result=Tasks.await(task,750,TimeUnit.MILLISECONDS)
   val age=TimeUnit.NANOSECONDS.toMillis(System.nanoTime()-capturedAt)
   synchronized(lock){if(closed)return null}
   if(age !in 0..2500 || jpeg.size>524288)return null
   val lines=JSONArray()
   for(block in result.textBlocks)for(line in block.lines) {
    if(lines.length()>=64)break
    val text=line.text.replace(Regex("[\\p{Cntrl}]")," ").trim()
    val b=line.boundingBox?:continue
    if(text.isEmpty()||text.length>160||b.left<0||b.top<0||b.right>frame.width||b.bottom>frame.height||b.left>=b.right||b.top>=b.bottom)continue
    lines.put(JSONObject().put("text",text).put("bounds",JSONArray(listOf(b.left,b.top,b.right,b.bottom))))
   }
   val sha=MessageDigest.getInstance("SHA-256").digest(jpeg).joinToString(""){"%02x".format(it)}
   return JSONObject().put("v",1).put("width",frame.width).put("height",frame.height)
    .put("ageMs",age).put("sha256",sha).put("lines",lines)
  } catch(_: Exception) {
   // Completion listener retains/recycles any in-flight image after timeout.
   if(!retained){if(!copy.isRecycled)copy.recycle();synchronized(lock){busy=false;if(closed){reader?.close();reader=null}}}
   return null
  }
 }
 fun close()=synchronized(lock){closed=true;if(!busy){reader?.close();reader=null}}
}
