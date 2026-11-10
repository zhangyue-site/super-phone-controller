package org.example.phonecontroller

import android.app.KeyguardManager
import android.content.Context
import android.graphics.BitmapFactory
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.os.SystemClock
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.TextRecognizer
import com.google.mlkit.vision.text.chinese.ChineseTextRecognizerOptions
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** Ten fresh OCR frames on ANY page. Page classification is a separate result. */
class BillTextLoop(private val context: Context) {
 private val main=Handler(Looper.getMainLooper())
 private val worker=Executors.newSingleThreadExecutor()
 private var recognizer: TextRecognizer?=null
 private var generation=0
 private var busy=false
 private var active=false
 private var runId=""
 private var progress: RecognitionProgress?=null
 private var matched=0
 private var startAt=0L
 private var captureEpoch=0L
 var status="连续文字识别未开始"
  private set
 private val amount = Regex("(?<![0-9.])[+-]?[0-9]{1,7}(?:,[0-9]{3})*\\.[0-9]{2}(?![0-9.])")
 private val date = Regex("(?<![0-9])(?:20[0-9]{2}[年./-])?(1[0-2]|0?[1-9])[月./-](3[01]|[12][0-9]|0?[1-9])日?(?![0-9])")

 private fun unlocked()=context.getSystemService(PowerManager::class.java).isInteractive &&
  !context.getSystemService(KeyguardManager::class.java).isKeyguardLocked
 fun start(delayed: Boolean = false): Boolean {
  if(active)return true
  if(busy||!ScreenShareService.active||!unlocked()){status="请先解锁并开启屏幕共享";return false}
  val lease=ScreenShareService.beginRecognition("ocr") ?: run {status="另一轮识别正在运行，或共享连接未就绪";return false}
  runId=lease.first;captureEpoch=lease.second;progress=null
  startAt=SystemClock.elapsedRealtime()+if(delayed) 8000L else 0L
  matched=0;active=true;generation++
  status=if(delayed) "8 秒后开始，可切换到待识别页面" else "正在识别 0 / 10 帧"
  WorkbenchDiagnostics.beginRecognition()
  record("ocr_start");main.post(tick);return true
 }
 fun stop()=finish("stopped")
 fun close(){finish("closed");worker.shutdown()}
 private fun record(stage: String,value: Int=0)=WorkbenchDiagnostics.record(stage,progress?.count()?:0,value)
 private fun closeRecognizer(){recognizer?.close();recognizer=null}
 private fun finish(reason: String){
  if(!active)return
  active=false;generation++;main.removeCallbacks(tick)
  progress?.stop(reason)
  RecognitionEvidence.finish(runId,reason);ScreenShareService.endRecognition(runId)
  val stage=when(reason){"done"->"ocr_done";"timeout","frame_timeout","inference_timeout"->"ocr_timeout";"error"->"ocr_error";else->"ocr_stop"}
  record(stage)
  val label=when(reason){"done"->"连续识别完成";"frame_timeout"->"没有收到新的共享帧";"inference_timeout"->"本帧识别超时";"timeout"->"达到本轮时间上限";"capture_changed"->"共享会话已改变";"locked"->"手机锁屏或共享已结束";"error"->"本地文字识别失败";else->"本轮已停止"}
  status="$label：已识别 ${progress?.count()?:0} / 10 帧，账单类 $matched 帧"
  if(!busy)closeRecognizer()
 }
 private val tick=object: Runnable {
  override fun run(){
   if(!active)return
   if(!ScreenShareService.active||!unlocked()){finish("locked");return}
   if(!ScreenShareService.recognitionLive(runId)){finish("capture_changed");return}
   val now=SystemClock.elapsedRealtime()
   if(now<startAt){
    status="${(startAt-now+999)/1000} 秒后开始，可切换到待识别页面"
    main.postDelayed(this,250)
    return
   }
   val p=progress?:RecognitionProgress(captureEpoch,now,System.nanoTime()).also{
    progress=it
    status="正在识别 0 / 10 帧"
   }
   p.poll(now)
   if(p.state()!="running"){finish(p.state());return}
   val frame=ScreenShareService.latestLoopFrame
   if(!busy&&frame!=null){
    val age=TimeUnit.NANOSECONDS.toMillis(System.nanoTime()-frame.capturedAt)
    if(p.offer(frame.capturedAt,age,frame.captureEpoch,now)){
     busy=true;val g=generation
     worker.execute{recognize(frame,g,age)}
    } else if(p.state()!="running"){finish(p.state());return}
   }
   main.postDelayed(this,250)
  }
 }
 private fun recognize(frame: LoopFrame,g: Int,age: Long){
  val started=SystemClock.elapsedRealtime()
  val bitmap=BitmapFactory.decodeByteArray(frame.jpeg,0,frame.jpeg.size)
  if(bitmap==null){main.post{result(g,frame,age,null,0)};return}
  try {
   val reader=recognizer?:TextRecognition.getClient(ChineseTextRecognizerOptions.Builder().build()).also{recognizer=it}
   // Deliver every completion on the same main executor; the worker does not block.
   reader.process(InputImage.fromBitmap(bitmap,0)).addOnCompleteListener { task ->
    bitmap.recycle()
    main.post {result(g,frame,age,if(task.isSuccessful)task.result.text else null,
     (SystemClock.elapsedRealtime()-started).coerceIn(0,60000).toInt())}
   }
  } catch(_: Exception){bitmap.recycle();main.post{result(g,frame,age,null,0)}}
 }
 private fun result(g: Int,frame: LoopFrame,age: Long,text: String?,elapsed: Int){
  busy=false
  if(!active||g!=generation){closeRecognizer();return}
  if(!ScreenShareService.active||!unlocked()){finish("locked");return}
  if(!ScreenShareService.recognitionLive(runId)){finish("capture_changed");return}
  val p=progress?:return
  if(text==null){finish("error");return}
  if(!p.complete(frame.capturedAt,SystemClock.elapsedRealtime())){finish(p.state());return}
  val compact=text.replace(Regex("\\s+"),"")
  val dates = date.findAll(compact).map { it.groupValues[1].toInt()*100+it.groupValues[2].toInt() }.distinct().take(2).toList()
  val amounts = amount.findAll(text).mapNotNull {
   it.value.trimStart('+','-').replace(",","").replace(".","").toIntOrNull()
  }.filter { it in 1..999999999 }.distinct().take(4).toList()
  val page=BillPageClassifier.classify(compact,amount.containsMatchIn(text))
  val achai=page=="achai"
  val bill=page=="bill"
  if(page!="other")matched++
  RecognitionEvidence.preview(runId,text)
  if(!RecognitionEvidence.frame(runId,frame,age,elapsed,text.lineSequence().count(),page)){
   finish("capture_changed");return
  }
  // Keep existing v52 diagnostics compatible; count successful frames, not matches.
  record(if(achai)"ocr_achai" else if(bill)"ocr_bill" else "ocr_other",text.lineSequence().count().coerceAtMost(60000))
  record("ocr_ms",elapsed)
  if(page!="other") {
   dates.forEach { record("ocr_date",it) }
   amounts.forEach { record("ocr_amount",it) }
   if(achai && "该账单已添加" in compact)record("ocr_added",1)
  }
  status="已识别 ${p.count()} / 10 帧 · 账单类 $matched 帧 · ${elapsed}ms"
  if(p.state()=="done")finish("done")
 }
}
