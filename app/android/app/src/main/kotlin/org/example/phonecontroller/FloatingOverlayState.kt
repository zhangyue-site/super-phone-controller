package org.example.phonecontroller

import kotlin.math.hypot
import kotlin.math.roundToInt

/** Platform-neutral geometry and window lifecycle shared by floating controls. */
internal data class OverlayBounds(val left: Int, val top: Int, val right: Int, val bottom: Int) {
    fun position(x: Int, y: Int, width: Int, height: Int): Pair<Int, Int> =
        x.coerceIn(left, maxOf(left, right - width)) to
            y.coerceIn(top, maxOf(top, bottom - height))
    fun restore(fx: Float, fy: Float, width: Int, height: Int): Pair<Int, Int> = position(
        left + (maxOf(0, right - left - width) * fx.coerceIn(0f, 1f)).roundToInt(),
        top + (maxOf(0, bottom - top - height) * fy.coerceIn(0f, 1f)).roundToInt(), width, height)
    fun fraction(x: Int, y: Int, width: Int, height: Int): Pair<Float, Float> =
        ((x - left).toFloat() / maxOf(1, right - left - width)).coerceIn(0f, 1f) to
            ((y - top).toFloat() / maxOf(1, bottom - top - height)).coerceIn(0f, 1f)
}

internal class OverlayDrag(private val slop: Int) {
    private var downX = 0f
    private var downY = 0f
    private var startX = 0
    private var startY = 0
    var dragging = false; private set
    fun down(rawX: Float, rawY: Float, x: Int, y: Int) {
        downX = rawX; downY = rawY; startX = x; startY = y; dragging = false
    }
    fun move(rawX: Float, rawY: Float): Pair<Int, Int>? {
        val dx = rawX - downX; val dy = rawY - downY
        if (!dragging && hypot(dx.toDouble(), dy.toDouble()) > slop) dragging = true
        return if (dragging) startX + dx.roundToInt() to startY + dy.roundToInt() else null
    }
    fun finish() { dragging = false }
}

/** A real window owner is injected, never inferred from View.parent (a ViewRootImpl). */
internal interface OverlayWindowPort { fun add(); fun update(x: Int, y: Int); fun remove() }
internal class OverlayWindowSession(private val port: OverlayWindowPort) {
    var attached = false; private set
    fun attach(): Boolean {
        if (attached) return true
        return try { port.add(); attached = true; true } catch (_: RuntimeException) { false }
    }
    fun move(x: Int, y: Int): Boolean {
        if (!attached) return false
        return try { port.update(x, y); true } catch (_: RuntimeException) { false }
    }
    fun detach() {
        if (!attached) return
        try { port.remove() } finally { attached = false }
    }
}
