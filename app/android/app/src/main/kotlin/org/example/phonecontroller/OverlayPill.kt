package org.example.phonecontroller

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.BatteryManager
import android.provider.Settings
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.TextView
import io.flutter.plugin.common.MethodChannel

/**
 * 被控端悬浮状态条（pill）。
 *
 * 渲染完全由 Flutter 驱动：pcflash/pill 通道的 show/update/hide 携带 4 个状态灯
 * 编码与三段文本，本文件只负责窗口管理与手势（点按展开/收起、垂直拖动、关闭）。
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
        val wm = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val root = LinearLayout(context)
        root.orientation = LinearLayout.VERTICAL
        render(context, root)
        val lp = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            PixelFormat.TRANSLUCENT
        )
        lp.gravity = Gravity.TOP or Gravity.CENTER_HORIZONTAL
        lp.y = dip(context, 28)
        try {
            wm.addView(root, lp)
        } catch (_: Exception) {
            return false
        }
        attachGestures(context, root, lp)
        view = root
        return true
    }

    fun update(context: Context, data: Map<*, *>): Boolean {
        payload = data
        val root = view ?: return show(context, data)
        render(context, root)
        return true
    }

    fun hide() {
        remove()
    }

    private fun remove() {
        val root = view ?: return
        view = null
        try {
            (root.parent as? WindowManager)?.removeView(root)
        } catch (_: Exception) {
        }
    }

    private fun closePill() {
        remove()
        try {
            notifier?.invokeMethod("onClosed", null)
        } catch (_: Exception) {
        }
    }

    /** 就地重建内容；窗口保持挂载，拖动位置不受影响。 */
    private fun render(context: Context, root: LinearLayout) {
        val data = payload ?: return
        root.removeAllViews()
        val background = GradientDrawable()
        background.setColor(Color.argb(217, 22, 24, 27))
        background.cornerRadius =
            dip(context, if (expanded) 14 else 20).toFloat()
        root.background = background
        root.setPadding(
            dip(context, 12),
            dip(context, if (expanded) 8 else 6),
            dip(context, 12),
            dip(context, if (expanded) 10 else 6)
        )
        if (expanded) {
            root.addView(headerRow(context, data, withClose = true))
            root.addView(line(context, text(data, "line1")))
            root.addView(line(context, text(data, "line2"), dim = true))
        } else {
            root.addView(headerRow(context, data, withClose = false))
        }
    }

    private fun headerRow(
        context: Context,
        data: Map<*, *>,
        withClose: Boolean
    ): LinearLayout {
        val row = LinearLayout(context)
        row.orientation = LinearLayout.HORIZONTAL
        row.gravity = Gravity.CENTER_VERTICAL
        for (key in listOf("battery", "share", "hid", "task")) {
            row.addView(dotView(context, dotColor(dot(data, key))))
        }
        if (withClose) {
            val close = label(context, "关闭", size = 13f)
            close.setPadding(dip(context, 16), dip(context, 2), 0, dip(context, 2))
            close.setOnClickListener { closePill() }
            row.addView(close)
        } else {
            val summary = label(context, text(data, "short"))
            summary.setPadding(dip(context, 8), 0, 0, 0)
            row.addView(summary)
        }
        return row
    }

    private fun line(context: Context, value: String, dim: Boolean = false): TextView {
        val view = label(context, value, dim = dim)
        view.setPadding(0, dip(context, 5), 0, 0)
        return view
    }

    private fun dotView(context: Context, color: Int): View {
        val view = View(context)
        val size = dip(context, 9)
        val lp = LinearLayout.LayoutParams(size, size)
        lp.rightMargin = dip(context, 5)
        view.layoutParams = lp
        val shape = GradientDrawable()
        shape.shape = GradientDrawable.OVAL
        shape.setColor(color)
        view.background = shape
        return view
    }

    /** 点按（未超过触摸阈值）切换展开；拖动只在垂直方向调整 lp.y。 */
    @SuppressLint("ClickableViewAccessibility")
    private fun attachGestures(
        context: Context,
        root: LinearLayout,
        lp: WindowManager.LayoutParams
    ) {
        val slop = ViewConfiguration.get(context).scaledTouchSlop
        var downRawY = 0f
        var startY = 0
        var dragging = false
        root.setOnTouchListener { _, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    downRawY = event.rawY
                    startY = lp.y
                    dragging = false
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dy = (event.rawY - downRawY).toInt()
                    if (!dragging && (dy < -slop || dy > slop)) dragging = true
                    if (dragging) {
                        val metrics = root.resources.displayMetrics
                        val max = metrics.heightPixels - root.height - dip(context, 8)
                        lp.y = (startY + dy).coerceIn(0, if (max > 0) max else 0)
                        try {
                            (root.parent as? WindowManager)?.updateViewLayout(root, lp)
                        } catch (_: Exception) {
                        }
                    }
                    true
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    val tapped = !dragging && event.actionMasked == MotionEvent.ACTION_UP
                    dragging = false
                    if (tapped) {
                        expanded = !expanded
                        render(context, root)
                    }
                    true
                }
                else -> false
            }
        }
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
