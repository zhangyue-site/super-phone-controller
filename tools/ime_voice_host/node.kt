package android.view.accessibility

import android.os.Bundle

class AccessibilityNodeInfo(
    var windowId: Int = 1, var packageName: CharSequence? = "app", var isVisibleToUser: Boolean = true,
    var isEnabled: Boolean = true, var isEditable: Boolean = true, var isFocused: Boolean = true,
    var isPassword: Boolean = false, var inputType: Int = 1
) {
    var focused: AccessibilityNodeInfo? = null
    val writes = mutableListOf<String>()
    fun findFocus(kind: Int): AccessibilityNodeInfo? { check(kind == FOCUS_INPUT); return focused }
    fun performAction(action: Int, args: Bundle): Boolean {
        check(action == ACTION_SET_TEXT)
        writes.add(checkNotNull(args.inserted).toString())
        return true
    }
    companion object {
        const val FOCUS_INPUT = 1
        const val ACTION_SET_TEXT = 2
        const val ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE = "text"
    }
}
