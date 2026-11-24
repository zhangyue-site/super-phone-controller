package android.os

class Bundle(private val text: String? = null) {
    fun getStringArrayList(key: String): ArrayList<String>? = text?.let { arrayListOf(it) }
}

object Build { object VERSION { var SDK_INT = 33 } }
class Looper { companion object { fun getMainLooper() = Looper() } }

class Handler(looper: Looper) {
    private val jobs = mutableListOf<Runnable>()
    init { all.add(this) }
    fun postDelayed(job: Runnable, delayMs: Long): Boolean { jobs.add(job); return true }
    fun removeCallbacks(job: Runnable) { jobs.remove(job) }
    companion object {
        private val all = mutableListOf<Handler>()
        fun expire() { for (handler in all) handler.jobs.toList().forEach { it.run() } }
    }
}
