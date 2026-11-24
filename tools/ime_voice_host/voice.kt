package android.speech

import android.content.Context
import android.content.Intent
import android.os.Bundle
import java.util.concurrent.Executor

interface RecognitionListener {
    fun onReadyForSpeech(params: Bundle?)
    fun onBeginningOfSpeech()
    fun onRmsChanged(rmsdB: Float)
    fun onBufferReceived(buffer: ByteArray?)
    fun onEndOfSpeech()
    fun onPartialResults(partialResults: Bundle?)
    fun onEvent(eventType: Int, params: Bundle?)
    fun onError(error: Int)
    fun onResults(results: Bundle?)
}

class RecognitionSupport(val installedOnDeviceLanguages: List<String>)
interface RecognitionSupportCallback {
    fun onSupportResult(support: RecognitionSupport)
    fun onError(error: Int)
}

object RecognizerIntent {
    const val ACTION_RECOGNIZE_SPEECH = "recognize"
    const val EXTRA_LANGUAGE_MODEL = "model"
    const val LANGUAGE_MODEL_FREE_FORM = "free"
    const val EXTRA_LANGUAGE = "language"
    const val EXTRA_PARTIAL_RESULTS = "partial"
    const val EXTRA_PREFER_OFFLINE = "offline"
}

class SpeechRecognizer {
    lateinit var listener: RecognitionListener
    fun setRecognitionListener(value: RecognitionListener) { listener = value }
    fun cancel() { }
    fun destroy() { }
    fun stopListening() { }
    fun startListening(intent: Intent) { }
    fun checkRecognitionSupport(intent: Intent, executor: Executor, callback: RecognitionSupportCallback) {
        val error = supportError
        if (error == null) callback.onSupportResult(RecognitionSupport(langs))
        else callback.onError(error)
    }
    companion object {
        const val RESULTS_RECOGNITION = "results"
        const val ERROR_LANGUAGE_NOT_SUPPORTED = 12
        const val ERROR_LANGUAGE_UNAVAILABLE = 13
        const val ERROR_CANNOT_CHECK_SUPPORT = 14
        var supportError: Int? = null
        const val ERROR_NO_MATCH = 7
        const val ERROR_SPEECH_TIMEOUT = 6
        const val ERROR_INSUFFICIENT_PERMISSIONS = 9
        var langs = listOf("zh-CN")
        var available = true
        lateinit var last: SpeechRecognizer
        fun isOnDeviceRecognitionAvailable(context: Context) = available
        fun createOnDeviceSpeechRecognizer(context: Context) = SpeechRecognizer().also { last = it }
    }
}
