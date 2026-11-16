package org.example.phonecontroller

import android.app.Activity
import android.app.KeyguardManager
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.os.SystemClock
import android.view.WindowManager

/** System trust (for example a nearby Bluetooth device) may dismiss keyguard.
 * No credential is collected, stored or entered; a secure locked device stays locked.
 */
class TaskWakeActivity: Activity() {
 private val handler=Handler(Looper.getMainLooper())
 private var deadline=0L
 private var requested=false
 override fun onCreate(savedInstanceState: Bundle?) {
  super.onCreate(savedInstanceState)
  if(Build.VERSION.SDK_INT>=27){setShowWhenLocked(true);setTurnScreenOn(true)}
  else window.addFlags(WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON)
  window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
  deadline=SystemClock.elapsedRealtime()+6000L
  handler.post(check)
 }
 private fun finishWake(reason: String) {
  SafeDiagnostics.record(mapOf("event" to "task_wake","phase" to "wake","reason" to reason))
  handler.removeCallbacksAndMessages(null)
  finishAndRemoveTask()
 }
 private val check: Runnable=object: Runnable {
  override fun run(){
   if(isFinishing)return
   val power=getSystemService(POWER_SERVICE) as PowerManager
   val keyguard=getSystemService(KEYGUARD_SERVICE) as KeyguardManager
   if(power.isInteractive && !keyguard.isKeyguardLocked){finishWake("unlocked");return}
   if(SystemClock.elapsedRealtime()>=deadline){finishWake("locked");return}
   if(power.isInteractive && !keyguard.isDeviceLocked && !requested){
    requested=true
    keyguard.requestDismissKeyguard(this@TaskWakeActivity,object: KeyguardManager.KeyguardDismissCallback(){
     override fun onDismissSucceeded(){handler.post(check)}
     override fun onDismissCancelled(){finishWake("locked")}
     override fun onDismissError(){finishWake("denied")}
    })
   }
   handler.postDelayed(this,150L)
  }
 }
 override fun onDestroy(){handler.removeCallbacksAndMessages(null);super.onDestroy()}
 companion object {
  fun request(context: Context) {
   try {
    context.startActivity(Intent(context,TaskWakeActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_NO_ANIMATION or Intent.FLAG_ACTIVITY_EXCLUDE_FROM_RECENTS))
    SafeDiagnostics.record(mapOf("event" to "task_wake","phase" to "wake","reason" to "requested"))
   } catch(_: Exception){SafeDiagnostics.record(mapOf("event" to "task_wake","phase" to "wake","reason" to "denied"))}
  }
 }
}
