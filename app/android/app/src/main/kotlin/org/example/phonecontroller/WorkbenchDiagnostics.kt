package org.example.phonecontroller

import java.util.ArrayDeque
import java.util.UUID

/** Fixed vocabulary and bounded counters for the authorized screen-status request. */
object WorkbenchDiagnostics {
 private var session=UUID.randomUUID().toString().take(8)
 private val stages = setOf("plugins","start","loaded","frame","boxes","wait","unavailable","stale","invalid","order","done","timeout","stop","failure","relay_error","ocr_start","ocr_bill","ocr_achai","ocr_other","ocr_ms","ocr_amount","ocr_date","ocr_added","ocr_done","ocr_timeout","ocr_stop","ocr_error")
 private val rows = ArrayDeque<String>()
 private var index = 0L

 @Synchronized fun beginRecognition(){session=UUID.randomUUID().toString().take(8);rows.clear();index=0L}
 @Synchronized fun record(stage: String?, count: Int?, value: Int?) {
  if (!BuildConfig.REMOTE_WORKBENCH_DIAGNOSTICS || stage !in stages ||
      count == null || count !in 0..10 || value == null || value !in 0..(if(stage=="ocr_amount")999999999 else 60000)) return
  if (rows.size == 40) rows.removeFirst()
  rows.addLast("${++index}:$stage:$count:$value")
 }

 @Synchronized fun snapshot(vararg capture: Long): String =
  "52;$session;${capture.joinToString(":") { it.coerceIn(0,999999999).toString() }};${rows.joinToString(",")}"
}
