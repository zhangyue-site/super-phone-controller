package android.view.inputmethod

class EditorInfo(var packageName: String = "notes", var inputType: Int = 1, var fieldId: Int = 2)
class InputConnection {
    val commits = mutableListOf<String>()
    fun commitText(value: String, newCursorPosition: Int): Boolean {
        commits.add(value)
        return true
    }
}
