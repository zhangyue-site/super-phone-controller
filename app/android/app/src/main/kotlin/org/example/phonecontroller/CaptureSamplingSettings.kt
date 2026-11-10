package org.example.phonecontroller
import android.content.Context
object CaptureSamplingSettings {
 fun enabled(context: Context)=context.getSharedPreferences("capture-sampling",Context.MODE_PRIVATE).getBoolean("enabled",false)
 fun setEnabled(context: Context,enabled: Boolean)=context.getSharedPreferences("capture-sampling",Context.MODE_PRIVATE).edit().putBoolean("enabled",enabled).commit()
}
