package org.example.phonecontroller

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognitionSupport
import android.speech.RecognitionSupportCallback
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.text.InputType
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection

/** Main-thread editor-bound dictation. Recognition can only produce a preview. */
class ImeVoiceDraft(private val ime: RelayImeService, private val render: () -> Unit) {
    enum class Phase { IDLE, CHECKING, LISTENING, FINISHING, PREVIEW }
    @Volatile var phase = Phase.IDLE
        private set
    var message = ""
        private set

    private val handler = Handler(Looper.getMainLooper())
    private var generation = 0L
    private var recognizer: SpeechRecognizer? = null
    private var target: InputConnection? = null
    private var pkg: String? = null
    private var field = 0
    private var type = 0
    private var text = ""
    private var timeout: Runnable? = null

    private fun onDeviceAvailable() = Build.VERSION.SDK_INT >= 31 &&
        runCatching { SpeechRecognizer.isOnDeviceRecognitionAvailable(ime) }.getOrDefault(false)

    fun offersPreviousKeyboard(): Boolean {
        val inputType = ime.currentInputEditorInfo?.inputType ?: return false
        return phase == Phase.IDLE && inputType != InputType.TYPE_NULL && !password(inputType) && !onDeviceAvailable()
    }

    fun action() {
        when (phase) {
            Phase.IDLE -> start()
            Phase.LISTENING -> {
                phase = Phase.FINISHING
                message = "正在整理听写"
                render()
                schedule(10_000)
                try { recognizer?.stopListening() } catch (_: Exception) { cancel("识别已停止，请重试") }
            }
            Phase.PREVIEW -> insert()
            else -> Unit
        }
    }

    fun cancel(label: String = "听写已取消") {
        generation++
        unschedule()
        val old = recognizer
        recognizer = null
        if (old != null) {
            runCatching { old.cancel() }
            runCatching { old.destroy() }
        }
        target = null
        pkg = null
        text = ""
        phase = Phase.IDLE
        message = label
        render()
    }

    fun invalidate() {
        if (phase != Phase.IDLE) cancel("输入会话已结束，草稿已清除") else message = ""
    }

    private fun start() {
        val info = ime.currentInputEditorInfo
        val connection = ime.currentInputConnection
        if (info == null || connection == null || !ime.isInputViewShown || info.inputType == InputType.TYPE_NULL) {
            cancel("请先点需要输入的文字框"); return
        }
        if (password(info.inputType)) { cancel("密码输入框无法听写"); return }
        if (!RelayInputOwner.takeManual(ime)) { cancel("远程动作正在收尾，请稍后再点听写"); return }
        if (!onDeviceAvailable()) {
            cancel("请在原键盘中点语音键开始听写")
            ime.returnToPreviousKeyboard()
            return
        }
        if (ime.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            cancel("请授权麦克风，返回原输入框后再点听写")
            try { ime.startActivity(Intent(ime, VoicePermissionActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
            catch (_: Exception) { cancel("请在系统应用设置中允许麦克风，再回到输入框") }
            return
        }
        val id = ++generation
        target = connection
        pkg = info.packageName
        field = info.fieldId
        type = info.inputType
        phase = Phase.CHECKING
        message = "正在检查离线识别"
        render()
        schedule(8_000)
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "zh-CN")
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
        }
        try {
            val engine = SpeechRecognizer.createOnDeviceSpeechRecognizer(ime)
            recognizer = engine
            engine.setRecognitionListener(object : RecognitionListener {
                override fun onReadyForSpeech(params: Bundle?) {}
                override fun onBeginningOfSpeech() {}
                override fun onRmsChanged(rmsdB: Float) {}
                override fun onBufferReceived(buffer: ByteArray?) {}
                override fun onEndOfSpeech() {
                    if (!valid(id) || phase != Phase.LISTENING) return
                    phase = Phase.FINISHING
                    message = "正在整理听写"
                    schedule(10_000)
                    render()
                }
                override fun onPartialResults(partialResults: Bundle?) {
                    if (!valid(id) || phase != Phase.LISTENING) return
                    val partial = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty()
                    if (partial.isNotBlank()) {
                        message = partial.filterNot { it.isISOControl() }.take(120)
                        render()
                    }
                }
                override fun onEvent(eventType: Int, params: Bundle?) {}
                override fun onError(error: Int) {
                    if (!valid(id) || phase == Phase.PREVIEW) return
                    val reason = when (error) {
                        SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED, SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE -> "本机缺少离线普通话，可切换键盘"
                        SpeechRecognizer.ERROR_NO_MATCH, SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "没有听清，请再说一次"
                        SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "麦克风未获授权，可重新授权"
                        else -> "本机听写暂不可用，可重试或切换键盘"
                    }
                    cancel(reason)
                }
                override fun onResults(results: Bundle?) {
                    if (!valid(id) || phase !in setOf(Phase.LISTENING, Phase.FINISHING)) return
                    val result = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.trim().orEmpty()
                    if (result.isBlank() || result.length > 2000 || result.any { it.isISOControl() }) {
                        cancel("未取得有效听写文字，请重试"); return
                    }
                    text = result
                    phase = Phase.PREVIEW
                    message = result
                    unschedule()
                    recognizer = null
                    runCatching { engine.destroy() }
                    schedule(60_000)
                    render()
                }
            })
            fun begin() {
                if (!valid(id) || phase != Phase.CHECKING) return
                phase = Phase.LISTENING
                message = "正在聆听"
                render()
                schedule(45_000)
                try { engine.startListening(intent) } catch (_: Exception) { cancel("离线识别启动失败，可重试") }
            }
            if (Build.VERSION.SDK_INT >= 33) {
                engine.checkRecognitionSupport(intent, ime.mainExecutor, object : RecognitionSupportCallback {
                    override fun onSupportResult(support: RecognitionSupport) {
                        if (!valid(id) || phase != Phase.CHECKING) return
                        val mandarin = support.installedOnDeviceLanguages.any {
                            val tag = it.replace('_', '-').lowercase(java.util.Locale.ROOT)
                            tag == "zh" || tag == "cmn" || tag.startsWith("cmn-") ||
                                tag == "zh-cn" || tag == "zh-sg" || tag.startsWith("zh-hans")
                        }
                        if (mandarin) begin() else cancel("本机尚无已安装的离线普通话，可切换键盘")
                    }
                    override fun onError(error: Int) {
                        if (!valid(id) || phase != Phase.CHECKING) return
                        if (error == SpeechRecognizer.ERROR_CANNOT_CHECK_SUPPORT) begin()
                        else cancel("无法核对离线普通话，可切换键盘")
                    }
                })
            } else begin() // API 31/32 has no language inventory. Offline-only recognition may reject zh-CN.
        } catch (_: Exception) { if (id == generation) cancel("本机离线听写暂不可用，可切换键盘") }
    }

    private fun attached(): Boolean {
        val info = ime.currentInputEditorInfo ?: return false
        return ime.isInputViewShown && ime.currentInputConnection === target && info.packageName == pkg &&
            info.fieldId == field && info.inputType == type && !password(info.inputType) && RelayInputOwner.isManual(ime)
    }

    private fun valid(id: Long): Boolean {
        if (id != generation || phase == Phase.IDLE) return false
        if (!attached()) { cancel("已切换输入框，草稿已清除"); return false }
        return true
    }

    private fun insert() {
        if (!valid(generation)) return
        val ic = target ?: return
        val draft = text
        cancel("正在插入") // invalidate callbacks before issuing the one permitted commit
        val ok = runCatching { ic.commitText(draft, 1) }.getOrDefault(false)
        message = if (ok) "已插入" else "输入框未接受文字，请检查原输入框"
        render()
    }

    private fun unschedule() { timeout?.let { handler.removeCallbacks(it) }; timeout = null }
    private fun schedule(ms: Long) {
        unschedule()
        val id = generation
        timeout = Runnable { if (id == generation) cancel("听写已超时，点听写可重新开始") }.also { handler.postDelayed(it, ms) }
    }

    companion object {
        fun password(type: Int): Boolean {
            val category = type and InputType.TYPE_MASK_CLASS
            val variant = type and InputType.TYPE_MASK_VARIATION
            return (category == InputType.TYPE_CLASS_TEXT && variant in setOf(
                InputType.TYPE_TEXT_VARIATION_PASSWORD, InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD,
                InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD)) ||
                (category == InputType.TYPE_CLASS_NUMBER && variant == InputType.TYPE_NUMBER_VARIATION_PASSWORD)
        }
    }
}
