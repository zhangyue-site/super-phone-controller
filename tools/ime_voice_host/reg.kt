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

    SpeechRecognizer.available = false
    f.draft.action()
    check(f.draft.phase == ImeVoiceDraft.Phase.IDLE)
    SpeechRecognizer.available = true
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
    println("PASS IME voice draft, focus, partial/final, retries, local-only capability, consent and ownership")
}
