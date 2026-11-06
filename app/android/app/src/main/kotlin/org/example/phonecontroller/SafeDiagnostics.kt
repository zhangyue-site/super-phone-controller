package org.example.phonecontroller
import android.content.Context
import android.os.SystemClock
import org.json.JSONArray
import org.json.JSONObject

/** Private bounded ring; timestamps originate here, never from caller payload. */
object SafeDiagnostics {
 private var app: Context?=null
 @Synchronized fun initialize(context: Context){app=context.applicationContext}
 @Synchronized fun record(raw: Map<*,*>){
  val safe=DiagnosticSchema.sanitize(raw);if(safe.isEmpty())return
  val context=app?:return
  val prefs=context.getSharedPreferences("safe-diagnostics",Context.MODE_PRIVATE)
  val rows=try{JSONArray(prefs.getString("events","[]"))}catch(_:Exception){JSONArray()}
  val event=JSONObject(safe).put("wall_ms",System.currentTimeMillis()).put("elapsed_ms",SystemClock.elapsedRealtime()).put("index",prefs.getLong("index",0)+1)
  rows.put(event)
  val bounded=JSONArray();for(i in maxOf(0,rows.length()-192) until rows.length())bounded.put(rows.getJSONObject(i))
  prefs.edit().putLong("index",event.getLong("index")).putString("events",bounded.toString()).commit()
  android.util.Log.i("PhoneDiag",event.toString())
 }
 @Synchronized fun read(): String = app?.getSharedPreferences("safe-diagnostics",Context.MODE_PRIVATE)?.getString("events","[]")?:"[]"
}
