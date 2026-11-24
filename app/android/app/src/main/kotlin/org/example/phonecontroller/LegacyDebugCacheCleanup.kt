package org.example.phonecontroller

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Erase the retired debugging guide's private storage on upgrade without reading its contents. */
class LegacyDebugCacheCleanup : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_MY_PACKAGE_REPLACED) clear(context)
    }
    companion object {
        fun clear(context: Context) {
            context.deleteSharedPreferences("adb-guide")
        }
    }
}
