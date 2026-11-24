package org.example.phonecontroller

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.provider.Settings

/** The permission dialog never captures audio or retains a reference to the previous editor. */
class VoicePermissionActivity : Activity() {
    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            finish()
        } else if (state == null) {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 47)
        } else if (state.getBoolean("settings")) {
            showSettingsHint()
        }
    }
    private var showingHint = false
    override fun onSaveInstanceState(state: Bundle) {
        state.putBoolean("settings", showingHint)
        super.onSaveInstanceState(state)
    }
    override fun onRequestPermissionsResult(code: Int, permissions: Array<out String>, results: IntArray) {
        super.onRequestPermissionsResult(code, permissions, results)
        if (code != 47) return
        if (results.firstOrNull() == PackageManager.PERMISSION_GRANTED ||
            shouldShowRequestPermissionRationale(Manifest.permission.RECORD_AUDIO)) finish()
        else showSettingsHint()
    }
    private fun showSettingsHint() {
        showingHint = true
        AlertDialog.Builder(this).setMessage("允许使用麦克风后，回到原输入框，再点一次听写。")
            .setPositiveButton("应用设置") { _, _ ->
                runCatching { startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + packageName))) }
                finish()
            }.setNegativeButton("返回") { _, _ -> finish() }
            .setOnCancelListener { finish() }.show()
    }
}
