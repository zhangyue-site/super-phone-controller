package org.example.phonecontroller

import android.os.Bundle
import android.view.accessibility.AccessibilityNodeInfo

/** A remote text command may use the editor with input focus, never a candidate found by traversal. */
internal object RelayEditorAccess {
    fun focusedEditor(root: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        val node = root?.findFocus(AccessibilityNodeInfo.FOCUS_INPUT) ?: return null
        return node.takeIf {
            it.windowId == root.windowId && it.packageName != null && it.isVisibleToUser && it.isEnabled &&
                it.isEditable && it.isFocused && !it.isPassword && !ImeVoiceDraft.password(it.inputType)
        }
    }

    fun setText(expected: AccessibilityNodeInfo?, current: () -> AccessibilityNodeInfo?, text: String): Boolean {
        if (expected == null || text.isEmpty()) return false
        val latest = current() ?: return false
        if (latest != expected) return false
        val args = Bundle().apply { putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text) }
        return latest.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
    }
}
