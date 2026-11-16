package org.example.phonecontroller

import android.view.View
import android.view.WindowManager

/** The exact WindowManager instance that added this view owns update and removal. */
internal class AndroidOverlayWindowPort(
    private val manager: WindowManager,
    private val view: View,
    private val params: WindowManager.LayoutParams
) : OverlayWindowPort {
    override fun add() { manager.addView(view, params) }
    override fun update(x: Int, y: Int) {
        params.x = x; params.y = y
        manager.updateViewLayout(view, params)
    }
    override fun remove() {
        try { manager.removeViewImmediate(view) }
        catch (_: IllegalArgumentException) { /* the window was already detached */ }
    }
}
