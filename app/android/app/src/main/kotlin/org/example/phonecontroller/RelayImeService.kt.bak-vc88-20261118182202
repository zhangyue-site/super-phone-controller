package org.example.phonecontroller

// RelayImeService — 输入法中转打字（paste_text / op=15）。
// 无 UI、无网络、不落日志；文本只在内存停留到 commit 为止。
// 一次性授权（见仓库 007_setup_adb.md）：
//   adb shell pm grant <applicationId> android.permission.WRITE_SECURE_SETTINGS
//   adb shell ime enable <applicationId>/org.example.phonecontroller.RelayImeService

import android.content.Context
import android.inputmethodservice.InputMethodService
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.KeyEvent
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection
import java.util.concurrent.CountDownLatch
import java.util.concurrent.LinkedBlockingDeque
import java.util.concurrent.TimeUnit

/** 无界面输入法：把云端整句文本 commitText 进当前焦点输入框。 */
class RelayImeService : InputMethodService() {

    data class Pending(val text: String, val enter: Boolean)

    interface CommitListener {
        /** ok=true 表示 InputConnection.commitText 已实际接受。 */
        fun onCommitted(text: String, ok: Boolean, reason: String?)
    }

    companion object {
        @Volatile
        var instance: RelayImeService? = null
            private set

        private val queue = LinkedBlockingDeque<Pending>()

        @Volatile
        private var listener: CommitListener? = null

        private val main = Handler(Looper.getMainLooper())

        const val SERVICE_CLASS = "org.example.phonecontroller.RelayImeService"

        fun connected(): Boolean = instance != null

        fun currentImeId(context: Context): String? =
            Settings.Secure.getString(context.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD)

        /** 入队一条待提交文本。返回 false = 服务未连接（调用方走等待/超时路径）。 */
        fun enqueue(text: String, enter: Boolean, l: CommitListener?): Boolean {
            if (text.isEmpty() || text.length > 256 || text.any { it.code < 0x20 || it.code == 0x7f }) return false
            synchronized(queue) {
                queue.clear()
                listener = l
                queue.offer(Pending(text, enter))
            }
            val svc = instance ?: return false
            main.post { svc.drain() }
            return true
        }

        fun cancelPending() {
            synchronized(queue) {
                queue.clear()
                listener?.onCommitted("", false, "cancelled")
                listener = null
            }
        }
    }

    override fun onCreate() {
        instance = this
        super.onCreate()
    }

    override fun onDestroy() {
        if (instance === this) instance = null
        cancelPending()
        super.onDestroy()
    }

    override fun onUnbind(intent: android.content.Intent?): Boolean {
        if (instance === this) instance = null
        return super.onUnbind(intent)
    }

    /** 无 UI：返回 null，系统不会渲染任何候选栏/键盘面板。 */
    override fun onCreateInputView(): android.view.View? = null

    override fun onStartInput(attribute: EditorInfo?, restarting: Boolean) {
        drain()
    }

    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        drain()
    }

    /** 只要有 InputConnection 就立刻消费队首。没有则等下一个 onStartInput。 */
    fun drain() {
        val head = synchronized(queue) { queue.peekFirst() } ?: return
        val ic: InputConnection = currentInputConnection ?: return
        val ok = ic.commitText(head.text, 1)
        if (ok && head.enter) {
            ic.sendKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_ENTER))
            ic.sendKeyEvent(KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_ENTER))
        }
        synchronized(queue) {
            queue.pollFirst()
            val l = listener
            listener = null
            l?.onCommitted(head.text, ok, null)
        }
        // 提交完即退场，避免系统一直挂着这个空输入法面板。
        requestHideSelf(0)
    }
}

/** paste 流程：切 IME → 等服务绑定 → enqueue → commit → 还原原输入法。
 *  全部在后台线程执行（IME 回调共享 App 主线程，绝不能在主线程等待）。 */
object RelayIme {

    private val main = Handler(Looper.getMainLooper())

    fun status(context: Context): Map<String, Any> {
        val app = context.applicationContext
        val authorized = app.checkSelfPermission(android.Manifest.permission.WRITE_SECURE_SETTINGS) ==
            android.content.pm.PackageManager.PERMISSION_GRANTED
        val selfId = app.packageName + "/" + RelayImeService.SERVICE_CLASS
        val enabled = Settings.Secure.getString(app.contentResolver, Settings.Secure.ENABLED_INPUT_METHODS) ?: ""
        return mapOf(
            "connected" to RelayImeService.connected(),
            "authorized" to authorized,
            "enabled" to enabled.split(':').contains(selfId),
            "currentIme" to (RelayImeService.currentImeId(app) ?: ""))
    }

    fun paste(context: Context, text: String, enter: Boolean, timeoutMs: Long, onDone: (Boolean, String?) -> Unit) {
        activateGuard()
        val app = context.applicationContext
        Thread {
            var ok = false
            var reason: String? = "paste_failed"
            var original: String? = null
            var switched = false
            val selfId = app.packageName + "/" + RelayImeService.SERVICE_CLASS
            try {
                val authorized = app.checkSelfPermission(android.Manifest.permission.WRITE_SECURE_SETTINGS) ==
                    android.content.pm.PackageManager.PERMISSION_GRANTED
                if (!authorized) { reason = "ime_not_authorized"; return@Thread }
                val enabled = Settings.Secure.getString(app.contentResolver, Settings.Secure.ENABLED_INPUT_METHODS) ?: ""
                if (!enabled.split(':').contains(selfId)) { reason = "ime_not_authorized"; return@Thread }
                original = RelayImeService.currentImeId(app)
                if (original == selfId) original = null
                if (original != null && !Settings.Secure.putString(app.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD, selfId)) {
                    reason = "ime_switch_failed"; return@Thread
                }
                switched = original != null
                // 等 IME 服务绑定（系统回调落在 App 主线程），最长 3s。
                var waited = 0L
                while (RelayImeService.instance == null && waited < 3000) {
                    Thread.sleep(100); waited += 100
                }
                val latch = CountDownLatch(1)
                val done = object : RelayImeService.CommitListener {
                    override fun onCommitted(t: String, success: Boolean, r: String?) {
                        ok = success; reason = r; latch.countDown()
                    }
                }
                val enqueued = RelayImeService.enqueue(text, enter, done)
                if (!enqueued) {
                    reason = if (RelayImeService.instance == null) "ime_switch_failed" else "paste_failed"
                    return@Thread
                }
                if (!latch.await(timeoutMs, TimeUnit.MILLISECONDS)) {
                    RelayImeService.cancelPending()
                    ok = false; reason = "paste_timeout"
                }
            } catch (t: Throwable) {
                ok = false; reason = "paste_failed"
            } finally {
                if (switched && !original.isNullOrEmpty() && original != selfId) {
                    runCatching {
                        Settings.Secure.putString(app.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD, original)
                    }
                }
            }
            main.post { onDone(ok, if (ok) null else (reason ?: "paste_failed")) }
        }.start()
    }
    private fun activateGuard() {}
    fun activate(context: Context): String? {
        val app = context.applicationContext
        if (app.checkSelfPermission(android.Manifest.permission.WRITE_SECURE_SETTINGS) != android.content.pm.PackageManager.PERMISSION_GRANTED) return null
        val selfId = "${app.packageName}/${RelayImeService.SERVICE_CLASS}"
        val cur = RelayImeService.currentImeId(app) ?: return null
        if (cur == selfId) return null
        val switched = Settings.Secure.putString(app.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD, selfId)
        if (switched) runCatching { java.io.File(app.filesDir, "ime_previous.txt").writeText(cur) }
        return if (switched) cur else null
    }
    fun restore(context: Context, id: String) {
        if (id.isEmpty()) return
        runCatching {
            Settings.Secure.putString(context.applicationContext.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD, id)
            java.io.File(context.applicationContext.filesDir, "ime_previous.txt").delete()
        }
    }
    fun recoverIfStuck(context: Context) {
        val app = context.applicationContext
        val selfId = "${app.packageName}/${RelayImeService.SERVICE_CLASS}"
        val cur = RelayImeService.currentImeId(app) ?: return
        if (cur != selfId) { java.io.File(app.filesDir, "ime_previous.txt").delete(); return }
        val f = java.io.File(app.filesDir, "ime_previous.txt")
        if (!f.exists()) return
        val prev = runCatching { f.readText().trim() }.getOrNull() ?: return
        if (prev.isEmpty() || prev == selfId) return
        runCatching {
            Settings.Secure.putString(app.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD, prev)
            f.delete()
        }
    }
}
