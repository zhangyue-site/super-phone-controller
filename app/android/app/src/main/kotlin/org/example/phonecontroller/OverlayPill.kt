package org.example.phonecontroller

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.BatteryManager
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import io.flutter.plugin.common.MethodChannel

/**
 * 被控端悬浮状态条（pill）。
 *
 * 渲染完全由 Flutter 驱动：pcflash/pill 通道的 show/update/hide 携带 4 个状态灯
 * 编码与三段文本，本文件只负责窗口管理与手势（点按展开/收起、二维拖动、关闭）。
 * 状态灯编码与 lib/overlay_pill.dart 的 pillGreen/pillYellow/pillRed/pillGray 对应。
 *
 * 生命周期约定：Activity 销毁（用户划掉任务、进程回收前）必须 remove，
 * 否则窗口会残留且无 Dart 端继续刷新。
 */
object OverlayPill {
    private const val GREEN = 0
    private const val YELLOW = 1
    private const val RED = 2
    private const val GRAY = 3

    private var view: LinearLayout? = null
    private var container: FloatingOverlayContainer? = null
    private var summary: TextView? = null
    private var line1: TextView? = null
    private var line2: TextView? = null
    private var body: LinearLayout? = null
    private var detailsScroll: android.widget.ScrollView? = null
    private var headerView: LinearLayout? = null
    private var closeButton: View? = null
    private var visualBar: LinearLayout? = null
    private var dots: List<View> = emptyList()
    private var expanded = false
    private var payload: Map<*, *>? = null
    private var notifier: MethodChannel? = null

    fun setNotifier(channel: MethodChannel?) {
        notifier = channel
    }

    fun canShow(context: Context): Boolean = Settings.canDrawOverlays(context)

    fun openSettings(context: Context): Boolean = try {
        context.startActivity(
            Intent(
                Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                Uri.parse("package:${context.packageName}")
            ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        )
        true
    } catch (_: Exception) {
        false
    }

    /** 系统电池广播是 sticky 的；无需接收器实例，也不需要新权限。 */
    fun battery(context: Context): Int? = try {
        val intent =
            context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val level = intent?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = intent?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
        if (level < 0 || scale <= 0) null else level * 100 / scale
    } catch (_: Exception) {
        null
    }

    fun show(context: Context, data: Map<*, *>): Boolean {
        if (!canShow(context)) return false
        remove()
        expanded = false
        payload = data
        val app = context.applicationContext
        val window = FloatingOverlayContainer(app, "status_pill")
        val content = LinearLayout(app).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, 0, 0, 0)
        }
        val header = LinearLayout(app).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            minimumHeight = dip(app, 48)
            isClickable = true; isFocusable = true
            setOnClickListener { toggle() }
        }
        val bar = LinearLayout(app).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setPadding(dip(app, 8), 0, dip(app, 8), 0)
        }
        header.addView(bar, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT, dip(app, 32)))
        visualBar = bar
        dots = listOf("battery", "share", "hid", "task").map { key ->
            dotView(app, dotColor(dot(data, key))).also { bar.addView(it) }
        }
        summary = label(app, "").apply {
            maxLines = 1; ellipsize = android.text.TextUtils.TruncateAt.END
            maxWidth = dip(app, 72)
            setPadding(dip(app, 4), 0, dip(app, 4), 0)
        }
        bar.addView(summary)
        val close = android.widget.Button(app).apply {
            text = "关闭"; contentDescription = "仅关闭浮窗，不停止共享或控制"
            minimumWidth = dip(app, 48); minimumHeight = dip(app, 48)
            minWidth = dip(app, 48); minHeight = dip(app, 48)
            setPadding(0, 0, 0, 0)
            visibility = View.GONE
            setOnClickListener { closePill() }
        }
        bar.addView(close, LinearLayout.LayoutParams(dip(app, 48), dip(app, 48)))
        closeButton = close
        // A real button preserves keyboard/TalkBack semantics; drags are intercepted by the shell.
        header.accessibilityDelegate = object : View.AccessibilityDelegate() {
            override fun onInitializeAccessibilityNodeInfo(host: View, info: android.view.accessibility.AccessibilityNodeInfo) {
                super.onInitializeAccessibilityNodeInfo(host, info)
                info.className = "android.widget.Button"
                info.isExpandedCompat(expanded)
            }
        }
        content.addView(header)
        val details = LinearLayout(app).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dip(app, 8), dip(app, 4), dip(app, 8), dip(app, 12))
            visibility = View.GONE
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
        }
        line1 = label(app, "", size = 14f).apply { setLineSpacing(dip(app, 4).toFloat(), 1f) }
        line2 = label(app, "", size = 14f, dim = true).apply {
            setPadding(0, dip(app, 4), 0, 0)
        }
        details.addView(line1); details.addView(line2)
        // Long content scrolls inside a bounded panel rather than exceeding the safe screen.
        val scroll = android.widget.ScrollView(app).apply {
            isFillViewport = false
            addView(details)
            visibility = View.GONE
            setOnTouchListener { view, event ->
                when (event.actionMasked) {
                    android.view.MotionEvent.ACTION_DOWN -> view.parent?.requestDisallowInterceptTouchEvent(true)
                    android.view.MotionEvent.ACTION_UP, android.view.MotionEvent.ACTION_CANCEL ->
                        view.parent?.requestDisallowInterceptTouchEvent(false)
                }
                false
            }
        }
        content.addView(scroll, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        body = details; detailsScroll = scroll; headerView = header
        window.root.addView(content)
        window.onToggle = { toggle() }
        window.onDismiss = { closePill() }
        container = window; view = content
        render(app, content)
        if (window.show()) return true
        remove()
        return false
    }

    fun update(context: Context, data: Map<*, *>): Boolean {
        payload = data
        val root = view ?: return show(context, data)
        render(root.context, root)
        return true
    }

    fun hide() { remove() }

    private fun remove() {
        container?.dismiss()
        container = null; view = null; summary = null; line1 = null; line2 = null
        body = null; detailsScroll = null; headerView = null; closeButton = null; visualBar = null; dots = emptyList()
    }

    private fun closePill() {
        remove()
        try { notifier?.invokeMethod("onClosed", null) } catch (_: Exception) { }
    }

    private fun toggle() {
        expanded = !expanded
        view?.let { render(it.context, it) }
        if (!expanded) headerView?.requestFocus()
    }

    /** Update fields in place: a polling update must not replace a pressed or focused child. */
    private fun render(context: Context, root: LinearLayout) {
        val data = payload ?: return
        val shape = GradientDrawable().apply {
            setColor(Color.argb(235, 22, 24, 27)); cornerRadius = dip(context, 16).toFloat()
        }
        root.background = if (expanded) shape else null
        root.setPadding(if (expanded) dip(context, 8) else 0, 0,
            if (expanded) dip(context, 8) else 0, 0)
        visualBar?.let { bar ->
            bar.background = if (expanded) null else shape
            val lp = bar.layoutParams
            val height = dip(context, if (expanded) 48 else 32)
            if (lp.height != height) { lp.height = height; bar.layoutParams = lp }
        }
        listOf("battery", "share", "hid", "task").forEachIndexed { index, key ->
            (dots.getOrNull(index)?.background as? GradientDrawable)?.setColor(dotColor(dot(data, key)))
        }
        summary?.text = text(data, "short").ifBlank { "状态" } + if (expanded) " ▴" else " ▾"
        line1?.text = text(data, "line1")
        line2?.text = text(data, "line2")
        headerView?.contentDescription = if (expanded) "点按收起状态详情" else
            listOf(text(data, "short"), text(data, "line1").replace('\n', '，'),
                text(data, "line2"), "点按展开状态详情").filter { it.isNotBlank() }.joinToString("，")
        body?.visibility = if (expanded) View.VISIBLE else View.GONE
        body?.importantForAccessibility = if (expanded) View.IMPORTANT_FOR_ACCESSIBILITY_AUTO
            else View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
        detailsScroll?.visibility = if (expanded) View.VISIBLE else View.GONE
        closeButton?.visibility = if (expanded) View.VISIBLE else View.GONE
        root.minimumWidth = dip(context, if (expanded) 220 else 0)
        container?.root?.contentDescription = if (expanded) "状态浮窗，已展开" else "状态浮窗，已收起"
        container?.root?.requestLayout()
    }

    private fun android.view.accessibility.AccessibilityNodeInfo.isExpandedCompat(value: Boolean) {
        // State description is available on current devices; click remains usable on API 26+.
        if (android.os.Build.VERSION.SDK_INT >= 30) stateDescription = if (value) "已展开" else "已收起"
    }

    private fun dotView(context: Context, color: Int): View = View(context).apply {
        val size = dip(context, 8)
        layoutParams = LinearLayout.LayoutParams(size, size).apply { rightMargin = dip(context, 4) }
        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(color) }
    }

    private fun dotColor(code: Int): Int = when (code) {
        GREEN -> Color.rgb(76, 175, 80)
        YELLOW -> Color.rgb(255, 193, 7)
        RED -> Color.rgb(244, 67, 54)
        else -> Color.rgb(158, 158, 158)
    }

    private fun dot(data: Map<*, *>, key: String): Int =
        (data[key] as? Number)?.toInt() ?: GRAY

    private fun text(data: Map<*, *>, key: String): String =
        data[key] as? String ?: ""

    private fun label(
        context: Context,
        value: String,
        size: Float = 12f,
        dim: Boolean = false
    ): TextView {
        val view = TextView(context)
        view.text = value
        view.textSize = size
        view.setTextColor(if (dim) Color.argb(204, 255, 255, 255) else Color.WHITE)
        return view
    }

    private fun dip(context: Context, value: Int): Int =
        (value * context.resources.displayMetrics.density + 0.5f).toInt()
}
