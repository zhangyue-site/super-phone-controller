package android.content

import java.util.concurrent.Executor

open class Context {
    val mainExecutor = Executor { it.run() }
    val applicationContext get() = this
    private val preferences = Prefs()
    fun getSharedPreferences(name: String, mode: Int) = preferences
    companion object { const val MODE_PRIVATE = 0 }
}

class Prefs {
    private val values = mutableMapOf<String, Boolean>()
    fun getBoolean(key: String, default: Boolean) = values[key] ?: default
    fun edit() = this
    fun putBoolean(key: String, value: Boolean) = apply { values[key] = value }
    fun commit() = true
}

class Intent {
    constructor(action: String)
    constructor(context: Context, target: Class<*>)
    fun putExtra(key: String, value: Any) = this
    fun addFlags(flags: Int) = this
    companion object { const val FLAG_ACTIVITY_NEW_TASK = 1 }
}
