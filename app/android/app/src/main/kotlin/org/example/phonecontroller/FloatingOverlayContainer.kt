package org.example.phonecontroller

import android.content.ComponentCallbacks
import android.content.Context
import android.content.res.Configuration
import android.graphics.PixelFormat
import android.os.Build
import android.view.Gravity
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.WindowInsets
import android.view.WindowManager
import android.view.accessibility.AccessibilityNodeInfo
import android.widget.FrameLayout

/** Nonmodal, reusable overlay shell. Owns the WindowManager that actually added the window. */
internal class FloatingOverlayContainer(context: Context, positionKey: String) {
    private val app = context.applicationContext
    private val visualContext = if (Build.VERSION.SDK_INT >= 30) {
        val displays = app.getSystemService(Context.DISPLAY_SERVICE) as android.hardware.display.DisplayManager
        val display = displays.getDisplay(android.view.Display.DEFAULT_DISPLAY)
        app.createDisplayContext(display).createWindowContext(WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY, null)
    } else app
    private val wm = visualContext.getSystemService(Context.WINDOW_SERVICE) as WindowManager
    private val prefs = app.getSharedPreferences("floating_overlay_positions", Context.MODE_PRIVATE)
    private val key = positionKey
    private val drag = OverlayDrag(ViewConfiguration.get(app).scaledTouchSlop)
    private var fx = prefs.getFloat("$key.x", 1f)
    private var fy = prefs.getFloat("$key.y", 0.15f)
    private var activePointer = -1
    private var registered = false
    private var closed = false
    var onToggle: (() -> Unit)? = null
    var onDismiss: (() -> Unit)? = null
    private val params = WindowManager.LayoutParams(
        WindowManager.LayoutParams.WRAP_CONTENT, WindowManager.LayoutParams.WRAP_CONTENT,
        WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
        WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
            WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
        PixelFormat.TRANSLUCENT
    ).apply { gravity = Gravity.TOP or Gravity.LEFT }
    val root: FrameLayout = object : FrameLayout(visualContext) {
        override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
            val bounds = safeBounds()
            // Bound the content by available safe space, even at large font scales.
            val width = minOf(dp(280), maxOf(1, bounds.right - bounds.left))
            val height = maxOf(1, bounds.bottom - bounds.top)
            super.onMeasure(MeasureSpec.makeMeasureSpec(width, MeasureSpec.AT_MOST),
                MeasureSpec.makeMeasureSpec(height, MeasureSpec.AT_MOST))
        }
        override fun onInterceptTouchEvent(event: MotionEvent): Boolean {
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> begin(event)
                MotionEvent.ACTION_MOVE -> if (singlePointer(event)) {
                    if (drag.move(event.rawX, event.rawY) != null) return true
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> finish()
                MotionEvent.ACTION_POINTER_DOWN -> { activePointer = -1; drag.finish() }
            }
            return false
        }
        override fun onTouchEvent(event: MotionEvent): Boolean {
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> { begin(event); return true }
                MotionEvent.ACTION_MOVE -> if (singlePointer(event)) {
                    drag.move(event.rawX, event.rawY)?.let { move(it.first, it.second) }
                }
                MotionEvent.ACTION_UP -> {
                    val tapped = activePointer >= 0 && !drag.dragging
                    finish()
                    if (tapped) performClick()
                }
                MotionEvent.ACTION_CANCEL, MotionEvent.ACTION_POINTER_DOWN -> finish()
            }
            return true
        }
        override fun performClick(): Boolean { super.performClick(); onToggle?.invoke(); return true }
        override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
            val step = dp(24)
            when (keyCode) {
                KeyEvent.KEYCODE_DPAD_LEFT -> nudge(-step, 0)
                KeyEvent.KEYCODE_DPAD_RIGHT -> nudge(step, 0)
                KeyEvent.KEYCODE_DPAD_UP -> nudge(0, -step)
                KeyEvent.KEYCODE_DPAD_DOWN -> nudge(0, step)
                KeyEvent.KEYCODE_ESCAPE -> onDismiss?.invoke()
                else -> return super.onKeyDown(keyCode, event)
            }
            return true
        }
        override fun onInitializeAccessibilityNodeInfo(info: AccessibilityNodeInfo) {
            super.onInitializeAccessibilityNodeInfo(info)
            info.addAction(AccessibilityNodeInfo.AccessibilityAction(MOVE_LEFT, "向左移动浮窗"))
            info.addAction(AccessibilityNodeInfo.AccessibilityAction(MOVE_RIGHT, "向右移动浮窗"))
            info.addAction(AccessibilityNodeInfo.AccessibilityAction(MOVE_UP, "向上移动浮窗"))
            info.addAction(AccessibilityNodeInfo.AccessibilityAction(MOVE_DOWN, "向下移动浮窗"))
            info.addAction(AccessibilityNodeInfo.AccessibilityAction(ACTION_CLOSE, "关闭浮窗"))
        }
        override fun performAccessibilityAction(action: Int, args: android.os.Bundle?): Boolean {
            when (action) {
                MOVE_LEFT -> nudge(-dp(24), 0)
                MOVE_RIGHT -> nudge(dp(24), 0)
                MOVE_UP -> nudge(0, -dp(24))
                MOVE_DOWN -> nudge(0, dp(24))
                ACTION_CLOSE -> onDismiss?.invoke()
                else -> return super.performAccessibilityAction(action, args)
            }
            return true
        }
    }.apply {
        isClickable = true
        isFocusable = true
        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
        setOnApplyWindowInsetsListener { _, insets -> post { reflow() }; insets }
        addOnLayoutChangeListener { _, l, t, r, b, ol, ot, or, ob ->
            if (r - l != or - ol || b - t != ob - ot) reflow()
        }
    }
    private val session = OverlayWindowSession(AndroidOverlayWindowPort(wm, root, params))
    private val callbacks = object : ComponentCallbacks {
        override fun onConfigurationChanged(newConfig: Configuration) {
            root.requestLayout(); root.post { reflow() }
        }
        override fun onLowMemory() = Unit
    }
    fun show(): Boolean {
        if (closed) return false
        val bounds = safeBounds()
        val initial = bounds.restore(fx, fy, dp(128), dp(48))
        params.x = initial.first; params.y = initial.second
        if (!session.attach()) return false
        if (!registered) { app.registerComponentCallbacks(callbacks); registered = true }
        root.post { reflow() }
        return true
    }
    fun dismiss() {
        if (closed) return
        closed = true
        save()
        if (registered) { app.unregisterComponentCallbacks(callbacks); registered = false }
        try { session.detach() } finally {
            root.removeAllViews()
            onToggle = null; onDismiss = null
        }
    }
    fun reflow() {
        if (!session.attached || closed) return
        val point = safeBounds().restore(fx, fy, root.measuredWidth, root.measuredHeight)
        if (point.first != params.x || point.second != params.y) session.move(point.first, point.second)
    }
    private fun begin(event: MotionEvent) {
        activePointer = event.getPointerId(0)
        drag.down(event.rawX, event.rawY, params.x, params.y)
    }
    private fun singlePointer(event: MotionEvent): Boolean =
        activePointer >= 0 && event.pointerCount == 1 && event.getPointerId(0) == activePointer
    private fun finish() { if (drag.dragging) save(); drag.finish(); activePointer = -1 }
    private fun move(x: Int, y: Int) {
        val bounds = safeBounds()
        val point = bounds.position(x, y, root.width, root.height)
        if (session.move(point.first, point.second)) {
            val ratio = bounds.fraction(point.first, point.second, root.width, root.height)
            fx = ratio.first; fy = ratio.second
        }
    }
    private fun nudge(dx: Int, dy: Int) { move(params.x + dx, params.y + dy); save() }
    private fun save() { prefs.edit().putFloat("$key.x", fx).putFloat("$key.y", fy).apply() }
    @Suppress("DEPRECATION")
    private fun safeBounds(): OverlayBounds {
        val margin = dp(4)
        if (Build.VERSION.SDK_INT >= 30) {
            val metrics = wm.currentWindowMetrics
            val insets = metrics.windowInsets.getInsetsIgnoringVisibility(
                WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
            return OverlayBounds(insets.left + margin, insets.top + margin,
                maxOf(insets.left + margin, metrics.bounds.width() - insets.right - margin),
                maxOf(insets.top + margin, metrics.bounds.height() - insets.bottom - margin))
        }
        val metrics = android.util.DisplayMetrics()
        wm.defaultDisplay.getRealMetrics(metrics)
        val insets = root.rootWindowInsets
        val top = insets?.stableInsetTop ?: systemDimension("status_bar_height")
        val bottom = insets?.stableInsetBottom ?: systemDimension("navigation_bar_height")
        val left = insets?.stableInsetLeft ?: 0
        val right = insets?.stableInsetRight ?: 0
        return OverlayBounds(left + margin, top + margin,
            maxOf(left + margin, metrics.widthPixels - right - margin),
            maxOf(top + margin, metrics.heightPixels - bottom - margin))
    }
    private fun systemDimension(name: String): Int {
        val id = app.resources.getIdentifier(name, "dimen", "android")
        return if (id != 0) app.resources.getDimensionPixelSize(id) else 0
    }
    private fun dp(value: Int) = (value * app.resources.displayMetrics.density + 0.5f).toInt()
    companion object {
        private const val MOVE_LEFT = 0x01020001
        private const val MOVE_RIGHT = 0x01020002
        private const val MOVE_UP = 0x01020003
        private const val MOVE_DOWN = 0x01020004
        private const val ACTION_CLOSE = 0x01020005
    }
}
