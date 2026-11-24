package org.example.phonecontroller

import android.content.Context
import android.content.Intent
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection

class RelayImeService : Context() {
    var currentInputEditorInfo = EditorInfo()
    var currentInputConnection = InputConnection()
    var isInputViewShown = true
    var permission = 0
    var launched = 0
    fun checkSelfPermission(key: String) = permission
    fun startActivity(intent: Intent) { launched++ }
    fun hasVoiceDraft() = false
    companion object { var instance: RelayImeService? = null }
}
class VoicePermissionActivity
