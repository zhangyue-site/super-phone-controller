package org.example.phonecontroller

import android.content.ComponentName
import android.content.Context
import android.inputmethodservice.InputMethodService
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.provider.Settings
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.PopupMenu
import android.widget.TextView
import java.io.File

/** Same installed IME supports manual dictation and the existing remote text operation. */
class RelayImeService : InputMethodService() {
    companion object {
        @Volatile var instance: RelayImeService? = null
            private set
        const val SERVICE_CLASS = "org.example.phonecontroller.RelayImeService"
        fun connected() = instance != null
        fun currentImeId(c: Context): String? = Settings.Secure.getString(c.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD)
    }
    private val draft by lazy { ImeVoiceDraft(this, ::render) }
    @Volatile internal var editorGeneration = 0L
        private set
    private var action: Button? = null
    private var label: TextView? = null
    private var cancelButton: Button? = null
    fun hasVoiceDraft() = draft.phase != ImeVoiceDraft.Phase.IDLE
    /** MainActivity dispatches STOP on the main looper. A STOP never releases the manual takeover. */
    fun cancelVoiceForStop() {
        if (hasVoiceDraft()) draft.cancel("收到停止，听写草稿已清除")
    }

    override fun onCreate() { super.onCreate(); instance = this }
    override fun onDestroy() {
        editorGeneration++
        draft.invalidate()
        if (instance === this) instance = null
        super.onDestroy()
    }
    override fun onStartInput(info: EditorInfo?, restarting: Boolean) {
        editorGeneration++
        draft.invalidate()
        super.onStartInput(info, restarting)
    }
    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        render()
    }
    override fun onFinishInputView(finishingInput: Boolean) {
        editorGeneration++
        draft.invalidate()
        super.onFinishInputView(finishingInput)
    }
    override fun onFinishInput() {
        editorGeneration++
        draft.invalidate()
        super.onFinishInput()
    }
    override fun onWindowHidden() {
        editorGeneration++
        draft.invalidate()
        super.onWindowHidden()
    }
    override fun onUnbindInput() {
        editorGeneration++
        draft.invalidate()
        super.onUnbindInput()
    }

    private fun hardwareToolbarAllowed() = RelayInputOwner.allowHardwareToolbar(
        this, currentInputEditorInfo?.inputType,
        resources.configuration.keyboard != android.content.res.Configuration.KEYBOARD_NOKEYS)

    override fun onEvaluateInputViewShown() = super.onEvaluateInputViewShown() || hardwareToolbarAllowed()

    override fun onShowInputRequested(flags: Int, configChange: Boolean) =
        super.onShowInputRequested(flags, configChange) || hardwareToolbarAllowed()

    override fun onCreateInputView(): View {
        val outer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(10), dp(3), dp(10), dp(4))
        }
        label = TextView(this).apply { textSize = 14f; maxLines = 4; isVerticalScrollBarEnabled = true
            movementMethod = android.text.method.ScrollingMovementMethod.getInstance() }
        val header = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL }
        header.addView(label, LinearLayout.LayoutParams(0, -2, 1f))
        cancelButton = Button(this, null, android.R.attr.borderlessButtonStyle).apply {
            text = "取消"; minHeight = dp(48); setOnClickListener { draft.cancel() }
        }
        header.addView(cancelButton)
        header.addView(Button(this, null, android.R.attr.borderlessButtonStyle).apply {
            text = "更多"; minHeight = dp(48); contentDescription = "更多键盘选项"
            setOnClickListener { menu(it) }
        })
        outer.addView(header)
        val row = LinearLayout(this).apply { gravity = Gravity.CENTER; orientation = LinearLayout.HORIZONTAL }
        action = Button(this).apply { isAllCaps = false; minHeight = dp(48); setOnClickListener { draft.action() } }
        val previousKeyboard = Button(this).apply {
            text = "回原键盘"; isAllCaps = false; minHeight = dp(48)
            setOnClickListener {
                RelayInputOwner.takeManual(this@RelayImeService)
                draft.invalidate()
                returnToPreviousKeyboard()
            }
        }
        row.addView(action, LinearLayout.LayoutParams(0, -2, 1f))
        row.addView(previousKeyboard, LinearLayout.LayoutParams(0, -2, 1f))
        outer.addView(row)
        render()
        return outer
    }
    private fun dp(value: Int) = (value * resources.displayMetrics.density + .5f).toInt()
    private fun render() {
        val phase = draft.phase
        action?.text = when (phase) {
            ImeVoiceDraft.Phase.IDLE -> "语音输入"
            ImeVoiceDraft.Phase.CHECKING -> "检查中"
            ImeVoiceDraft.Phase.LISTENING -> "说完"
            ImeVoiceDraft.Phase.FINISHING -> "识别中"
            ImeVoiceDraft.Phase.PREVIEW -> "插入文字"
        }
        action?.isEnabled = phase !in setOf(ImeVoiceDraft.Phase.CHECKING, ImeVoiceDraft.Phase.FINISHING)
        cancelButton?.visibility = if (phase == ImeVoiceDraft.Phase.IDLE) View.GONE else View.VISIBLE
        label?.text = if (phase == ImeVoiceDraft.Phase.IDLE && RelayInputOwner.isManual(this))
            draft.message + " · 远程已暂停，可在更多中恢复"
        else draft.message
    }
    private fun menu(anchor: View) {
        PopupMenu(this, anchor).apply {
            menu.add(0, 2, 1, "切换输入法")
            if (RelayInputOwner.isManual(this@RelayImeService)) menu.add(0, 3, 2, "恢复远程输入")
            setOnMenuItemClickListener {
                when (it.itemId) {
                    2 -> { RelayInputOwner.takeManual(this@RelayImeService); draft.invalidate(); showKeyboardPicker() }
                    3 -> {
                        draft.cancel("已结束本人听写")
                        if (RelayInputOwner.resumeRemote(this@RelayImeService)) label?.text = "已恢复远程输入"
                        else label?.text = "远程状态尚未就绪，稍后可重试"
                    }
                }
                true
            }
        }.show()
    }
    @Suppress("DEPRECATION")
    private fun returnToPreviousKeyboard() {
        val restored = runCatching {
            if (Build.VERSION.SDK_INT >= 28) switchToPreviousInputMethod()
            else {
                val imm = getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
                window?.window?.attributes?.token?.let { imm.switchToLastInputMethod(it) } == true
            }
        }.getOrDefault(false)
        if (!restored) showKeyboardPicker()
    }

    private fun showKeyboardPicker() {
        val imm = getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        imm.showInputMethodPicker()
    }
}

/** Composition and accessibility both use the same per-command owner as board HID. */
object RelayIme {
    private val main = Handler(Looper.getMainLooper())
    private fun self(c: Context) = ComponentName(c, RelayImeService::class.java)
    private fun same(a: String?, b: ComponentName) = a != null && ComponentName.unflattenFromString(a) == b
    private fun enabled(c: Context) =
        (c.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager).enabledInputMethodList
    private fun previousFile(c: Context) = File(c.filesDir, "ime_previous.txt")
    private fun authorized(c: Context) = c.checkSelfPermission(android.Manifest.permission.WRITE_SECURE_SETTINGS) ==
        android.content.pm.PackageManager.PERMISSION_GRANTED

    fun status(context: Context): Map<String, Any> = mapOf(
        "connected" to RelayImeService.connected(),
        "authorized" to authorized(context),
        "enabled" to enabled(context).any { same(it.id, self(context)) },
        "currentIme" to RelayImeService.currentImeId(context).orEmpty(),
        "manualTakeover" to RelayInputOwner.isManual(context))

    fun activate(context: Context): String? {
        val c = context.applicationContext
        if (RelayInputOwner.isManual(c) || !authorized(c) || enabled(c).none { same(it.id, self(c)) }) return null
        val current = RelayImeService.currentImeId(c) ?: return null
        if (same(current, self(c))) return null
        return runCatching {
            previousFile(c).writeText(current)
            if (Settings.Secure.putString(c.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD, self(c).flattenToString())) current
            else { previousFile(c).delete(); null }
        }.getOrNull()
    }

    fun restore(context: Context, id: String) {
        val c = context.applicationContext
        if (id.isBlank() || RelayInputOwner.isManual(c)) return
        runCatching {
            val saved = previousFile(c)
            if (!saved.exists() || saved.readText().trim() != id) return
            if (!same(RelayImeService.currentImeId(c), self(c))) { saved.delete(); return }
            val previous = ComponentName.unflattenFromString(id) ?: return
            if (previous == self(c) || enabled(c).none { same(it.id, previous) }) return
            if (Settings.Secure.putString(c.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD, id)) saved.delete()
        }
    }
    fun recoverIfStuck(context: Context) {
        val c = context.applicationContext
        if (RelayInputOwner.isManual(c)) return
        val previous = runCatching { previousFile(c).readText().trim() }.getOrNull() ?: return
        restore(c, previous)
    }

    fun paste(context: Context, text: String, enter: Boolean, timeoutMs: Long, remoteToken: Long? = null,
              onDone: (Boolean, String?) -> Unit) {
        val c = context.applicationContext
        if (text.isEmpty() || text.length > 256 || text.any { it.isISOControl() }) {
            onDone(false, "bad_text"); return
        }
        val token = remoteToken ?: RelayInputOwner.tryBeginRemote(c)
        if (token == null || !RelayInputOwner.permits(c, token)) { onDone(false, "manual_or_busy"); return }
        val deadline = SystemClock.elapsedRealtime() + timeoutMs.coerceIn(1, 8_000)
        val previous = RelayImeService.instance?.takeIf { same(RelayImeService.currentImeId(c), self(c)) }
        val previousGeneration = previous?.editorGeneration
        val previousConnection = previous?.currentInputConnection
        val previousField = previous?.currentInputEditorInfo?.takeIf {
            previousConnection != null && it.inputType != android.text.InputType.TYPE_NULL
        }
        val focused = AccessibilityAssistService.focusedEditor()
        val expectedPackage = focused?.packageName?.toString()
        var switchedFrom: String? = null
        var completed = false
        fun finish(ok: Boolean, reason: String?) {
            if (completed) return
            completed = true
            try { switchedFrom?.let { restore(c, it) } }
            finally {
                if (remoteToken == null) RelayInputOwner.endRemote(token)
                onDone(ok, reason)
            }
        }
        // All checks and the physical commit run on the same looper as manual takeover and focus changes.
        fun commitWhenBound() {
            if (!RelayInputOwner.permits(c, token)) { finish(false,"manual_or_busy"); return }
            if (SystemClock.elapsedRealtime() >= deadline) { finish(false,"paste_timeout"); return }
            val svc = RelayImeService.instance
            val ic = svc?.currentInputConnection
            val editor = svc?.currentInputEditorInfo
            if (focused != null && focused != AccessibilityAssistService.focusedEditor()) {
                finish(false, "editor_changed"); return
            }
            if (previousField != null && (previous !== svc || previousGeneration != svc?.editorGeneration ||
                        previousConnection !== ic)) {
                finish(false,"editor_changed"); return
            }
            if (svc == null || ic == null || editor == null) {
                main.postDelayed({ commitWhenBound() }, 80); return
            }
            if (editor.inputType == android.text.InputType.TYPE_NULL ||
                (focused != null && editor.packageName != expectedPackage)) { finish(false, "editor_changed"); return }
            if (ImeVoiceDraft.password(editor.inputType)) { finish(false, "password_field"); return }
            try {
                val ok = ic.commitText(text, 1)
                if (ok && enter) {
                    ic.sendKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_ENTER))
                    ic.sendKeyEvent(KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_ENTER))
                }
                if (ok) svc.requestHideSelf(0)
                finish(ok, if (ok) null else "paste_failed")
            } catch (_: Exception) { finish(false, "paste_unknown") }
        }
        main.post {
            if (!RelayInputOwner.permits(c, token)) { finish(false,"manual_or_busy"); return@post }
            try {
                if (focused != null) {
                    val applied = try { AccessibilityAssistService.setFocusedText(focused, text) }
                        catch (_: Exception) { finish(false, "paste_unknown"); return@post }
                    if (applied) { finish(true, null); return@post }
                    if (focused != AccessibilityAssistService.focusedEditor()) { finish(false, "editor_changed"); return@post }
                }
                // Without an original editor identity, a future connection could belong to any app.
                if (focused == null && previousField == null) { finish(false,"editor_unconfirmed"); return@post }
                if (!same(RelayImeService.currentImeId(c), self(c))) {
                    if (!authorized(c) || enabled(c).none { same(it.id, self(c)) }) { finish(false,"ime_not_authorized"); return@post }
                    switchedFrom = activate(c)
                    if (switchedFrom == null) { finish(false,"ime_switch_failed"); return@post }
                }
                commitWhenBound()
            } catch (_: Exception) { finish(false,"paste_failed") }
        }
    }
}
