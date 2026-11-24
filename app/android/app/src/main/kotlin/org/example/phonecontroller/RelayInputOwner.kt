package org.example.phonecontroller

import android.content.Context

/** A manual takeover survives service restarts. Only an explicit user action releases it. */
object RelayInputOwner {
    private var active: Long? = null
    private var sequence = 0L
    private var forcedManual = false
    private fun prefs(c: Context) = c.applicationContext.getSharedPreferences("ime-ownership", Context.MODE_PRIVATE)

    @Synchronized fun isManual(c: Context) = forcedManual || prefs(c).getBoolean("manual", false)

    // Only extend the platform default for an editable field in the personally selected IME.
    // No window is shown proactively: hiding the keyboard still clears Android's show request.
    @Synchronized fun allowHardwareToolbar(c: Context, inputType: Int?, hardwareKeyboard: Boolean): Boolean =
        hardwareKeyboard && inputType != null && inputType != android.text.InputType.TYPE_NULL &&
            (active == null || isManual(c))

    @Synchronized fun takeManual(c: Context): Boolean {
        forcedManual = true
        prefs(c).edit().putBoolean("manual", true).commit()
        return active == null
    }

    @Synchronized fun resumeRemote(c: Context): Boolean {
        if (active != null || RelayImeService.instance?.hasVoiceDraft() == true) return false
        if (!prefs(c).edit().putBoolean("manual", false).commit()) return false
        forcedManual = false
        return true
    }

    @Synchronized fun tryBeginRemote(c: Context): Long? {
        if (active != null || isManual(c)) return null
        return (++sequence).also { active = it }
    }

    @Synchronized fun permits(c: Context, token: Long): Boolean = active == token && !isManual(c)
    @Synchronized fun endRemote(token: Long) { if (active == token) active = null }
}
