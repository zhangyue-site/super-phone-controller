package org.example.phonecontroller

import android.os.Bundle
import android.os.Handler
import android.speech.SpeechRecognizer
import android.view.inputmethod.InputConnection

/** Normal callbacks, stale callbacks and timeout delivery can be controlled independently. */
private class Fixture {
    val service = RelayImeService()
    val draft = ImeVoiceDraft(service) { }
    val recorder get() = SpeechRecognizer.last.listener
    val commits get() = service.currentInputConnection.commits

    fun begin() {
        draft.action()
        check(draft.phase == ImeVoiceDraft.Phase.LISTENING)
    }
}

fun main() {
    val f = Fixture()
    f.begin()
    f.recorder.onPartialResults(Bundle("部分结果"))
    check(f.draft.message == "部分结果" && f.commits.isEmpty())
    val first = f.recorder
    first.onResults(Bundle("你好"))
    check(f.draft.phase == ImeVoiceDraft.Phase.PREVIEW && f.commits.isEmpty())
    f.draft.action()
    first.onResults(Bundle("重复回调"))
    check(f.commits == listOf("你好") && f.draft.phase == ImeVoiceDraft.Phase.IDLE)

    f.begin()
    val cancelled = f.recorder
    f.draft.cancel()
    f.begin()
    cancelled.onPartialResults(Bundle("过时的临时结果"))
    cancelled.onResults(Bundle("过时的最终结果"))
    cancelled.onError(1)
    check(f.draft.phase == ImeVoiceDraft.Phase.LISTENING)
    f.recorder.onResults(Bundle("新会话"))
    f.draft.action()
    check(f.commits == listOf("你好", "新会话"))

    f.begin()
    val oldField = f.service.currentInputConnection
    f.service.currentInputConnection = InputConnection()
    f.recorder.onResults(Bundle("写错框"))
    check(f.draft.phase == ImeVoiceDraft.Phase.IDLE && f.commits.isEmpty())
    check(oldField.commits.size == 2)

    f.begin()
    f.draft.action()
    Handler.expire()
    f.recorder.onResults(Bundle("迟到的结果"))
    check(f.draft.phase == ImeVoiceDraft.Phase.IDLE && f.commits.isEmpty())

    f.service.permission = -1
    f.draft.action()
    check(f.draft.phase == ImeVoiceDraft.Phase.IDLE && f.service.launched == 1)
    f.service.permission = 0
    f.begin()
    f.draft.invalidate()
    f.recorder.onResults(Bundle("已隐藏"))
    check(f.draft.phase == ImeVoiceDraft.Phase.IDLE && f.commits.isEmpty())

    f.service.currentInputEditorInfo.inputType = 129 // Text password.
    f.draft.action()
    check(f.draft.phase == ImeVoiceDraft.Phase.IDLE)
    f.service.currentInputEditorInfo.inputType = 33 // Email address is not a password.
    f.begin()
    f.draft.cancel()

    // No system on-device provider: one tap hands over, without mic permission or a new recognizer.
    SpeechRecognizer.available = false
    f.service.permission = -1
    val previousEngine = SpeechRecognizer.last
    val previousLaunches = f.service.launched
    check(f.draft.offersPreviousKeyboard())
    f.draft.action()
    check(f.service.keyboardReturns == 1 && f.service.launched == previousLaunches)
    check(SpeechRecognizer.last === previousEngine && f.commits.isEmpty() && RelayInputOwner.isManual(f.service))
    f.service.currentInputEditorInfo.inputType = 129
    check(!f.draft.offersPreviousKeyboard())
    f.draft.action()
    check(f.service.keyboardReturns == 1 && f.draft.message == "密码输入框无法听写")
    f.service.currentInputEditorInfo.inputType = 0
    check(!f.draft.offersPreviousKeyboard())
    f.draft.action()
    check(f.service.keyboardReturns == 1)
    f.service.currentInputEditorInfo.inputType = 1
    f.service.isInputViewShown = false
    f.draft.action()
    check(f.service.keyboardReturns == 1)
    f.service.isInputViewShown = true
    check(RelayInputOwner.resumeRemote(f.service))
    val pending = checkNotNull(RelayInputOwner.tryBeginRemote(f.service))
    f.draft.action()
    check(f.service.keyboardReturns == 1 && !RelayInputOwner.permits(f.service, pending))
    RelayInputOwner.endRemote(pending)
    f.draft.action()
    check(f.service.keyboardReturns == 2)
    SpeechRecognizer.available = true
    android.os.Build.VERSION.SDK_INT = 28
    check(f.draft.offersPreviousKeyboard())
    f.draft.action()
    check(f.service.keyboardReturns == 3 && f.service.launched == previousLaunches && SpeechRecognizer.last === previousEngine)
    android.os.Build.VERSION.SDK_INT = 33
    check(!f.draft.offersPreviousKeyboard())
    f.service.permission = 0
    println("PASS previous keyboard voice handoff, password, hidden field, remote in flight and API 28")
    SpeechRecognizer.langs = listOf("en-US")
    f.draft.action()
    check(f.draft.phase == ImeVoiceDraft.Phase.IDLE)
    SpeechRecognizer.supportError = SpeechRecognizer.ERROR_CANNOT_CHECK_SUPPORT
    f.begin()
    f.recorder.onError(SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE)
    check(f.draft.phase == ImeVoiceDraft.Phase.IDLE && f.commits.isEmpty())
    SpeechRecognizer.supportError = null
    SpeechRecognizer.langs = listOf("zh-CN")
    f.begin()
    f.draft.cancel()

    check(RelayInputOwner.tryBeginRemote(f.service) == null)
    check(RelayInputOwner.resumeRemote(f.service))
    val token = checkNotNull(RelayInputOwner.tryBeginRemote(f.service))
    check(!RelayInputOwner.takeManual(f.service))
    check(!RelayInputOwner.permits(f.service, token))
    RelayInputOwner.endRemote(token)
    check(RelayInputOwner.tryBeginRemote(f.service) == null)
    val user = RelayImeService()
    check(RelayInputOwner.allowHardwareToolbar(user, 1, true))
    check(!RelayInputOwner.allowHardwareToolbar(user, 0, true))
    check(!RelayInputOwner.allowHardwareToolbar(user, 1, false))
    check(RelayInputOwner.resumeRemote(user))
    val cloudLease = checkNotNull(RelayInputOwner.tryBeginRemote(user))
    check(!RelayInputOwner.allowHardwareToolbar(user, 1, true))
    RelayInputOwner.endRemote(cloudLease)
    check(RelayInputOwner.allowHardwareToolbar(user, 1, true))

    val root = android.view.accessibility.AccessibilityNodeInfo()
    val editor = android.view.accessibility.AccessibilityNodeInfo()
    fun current() = RelayEditorAccess.focusedEditor(root)
    check(current() == null)
    root.focused = editor
    val pinned = current()
    check(pinned === editor && RelayEditorAccess.setText(pinned, ::current, "一次"))
    check(editor.writes == listOf("一次"))
    root.focused = android.view.accessibility.AccessibilityNodeInfo()
    check(!RelayEditorAccess.setText(pinned, ::current, "错框"))
    check(root.focused!!.writes.isEmpty())
    root.focused = editor
    editor.isPassword = true
    check(!RelayEditorAccess.setText(pinned, ::current, "不应写入密码框"))
    editor.isPassword = false
    editor.inputType = 129
    check(current() == null)
    editor.inputType = 1
    editor.isFocused = false
    check(current() == null)
    editor.isFocused = true
    editor.isVisibleToUser = false
    check(current() == null)
    editor.isVisibleToUser = true
    editor.windowId = 2
    check(current() == null && editor.writes == listOf("一次"))
    println("PASS hardware keyboard toolbar policy and focused accessibility writes")
    println("PASS IME voice draft, focus, partial/final, retries, local-only capability, consent and ownership")
}
