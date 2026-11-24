package org.example.phonecontroller

import android.app.Activity
import android.content.ClipData
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.content.pm.ApplicationInfo
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.provider.Settings
import androidx.core.content.FileProvider
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import java.net.URI
import java.security.MessageDigest
import java.util.concurrent.Executors
import javax.net.ssl.HttpsURLConnection

class VerifiedUpdateProvider : FileProvider()

internal class OfficialAppUpdater(private val activity: Activity) {
    companion object {
        // Serial across Activity recreation. Each transfer has its own unpublished partial file.
        private val worker = Executors.newSingleThreadExecutor()
    }

    private val app = activity.applicationContext
    private val pm = app.packageManager
    private val handler = Handler(Looper.getMainLooper())
    private val policy by lazy { OfficialUpdatePolicy(BuildConfig.DOWNLOAD_URL) }
    private val cache get() = File(app.cacheDir, "verified-app-updates")
    private var selection: OfficialRelease? = null
    private var state = "idle"
    private var operation: String? = null
    private val waiters = mutableListOf<MethodChannel.Result>()
    @Volatile private var epoch = 0L
    @Volatile private var received = 0L
    @Volatile private var verifying = false
    private var foreground = false
    private var closed = false
    private var installerOpen = false
    private var permissionRequested = false

    fun resumed() { foreground = true; installerOpen = false }
    fun paused() { foreground = false }

    fun close() {
        closed = true
        epoch++
        completeError("cancelled")
    }

    fun handle(call: MethodCall, result: MethodChannel.Result) {
        try {
            if (closed) throw UpdateFailure("foreground")
            when (call.method) {
                "status" -> result.success(snapshot())
                "cancel" -> {
                    if (operation == "download" || operation == "check") {
                        epoch++
                        completeError("cancelled")
                    }
                    result.success(snapshot("cancelled"))
                }
                "check", "download", "install", "openInstallSettings" -> {
                    if (!foreground || activity.isFinishing || activity.isDestroyed) throw UpdateFailure("foreground")
                    if (operation == call.method) { waiters.add(result); return }
                    if (operation != null) throw UpdateFailure("busy")
                    when (call.method) {
                        "check" -> check(result)
                        "download" -> download(result)
                        "install" -> install(result)
                        else -> openSettings(result)
                    }
                }
                else -> result.notImplemented()
            }
        } catch (e: UpdateFailure) { result.error(e.code, e.code, null) }
          catch (_: Exception) { result.error("unavailable", "unavailable", null) }
    }

    private fun currentInfo() = pm.getPackageInfo(app.packageName, 0)

    @Suppress("DEPRECATION")
    private fun code(info: PackageInfo) = if (Build.VERSION.SDK_INT >= 28) info.longVersionCode else info.versionCode.toLong()

    private fun snapshot(override: String? = null): Map<String, Any?> {
        val installed = currentInfo()
        val visible = when (operation) {
            "check" -> "checking"
            "download" -> if (verifying) "verifying" else "downloading"
            "install" -> "verifying"
            else -> state
        }
        val r = selection
        return mapOf("state" to (override ?: visible), "installedCode" to code(installed),
            "installedName" to installed.versionName.orEmpty(), "versionCode" to r?.code,
            "versionName" to r?.name, "bytes" to (r?.size ?: 0), "received" to received)
    }

    private fun begin(name: String, result: MethodChannel.Result): Long {
        operation = name; waiters.add(result); verifying = false; received = 0
        return ++epoch
    }
    private fun active(id: Long) { if (id != epoch) throw UpdateFailure("cancelled") }

    private fun complete(override: String? = null) {
        operation = null; verifying = false
        val responses = waiters.toList(); waiters.clear()
        val info = snapshot(override)
        responses.forEach { it.success(info) }
    }
    private fun completeError(reason: String) {
        operation = null; verifying = false; received = 0
        val responses = waiters.toList(); waiters.clear()
        responses.forEach { it.error(reason, reason, null) }
    }
    private fun submit(id: Long, action: () -> Unit) {
        worker.execute {
            try { active(id); action() }
            catch (e: Exception) {
                val reason = when (e) { is UpdateFailure -> e.code; is IOException -> "network"; else -> "verification" }
                handler.post { if (id == epoch && !closed) completeError(reason) }
            }
        }
    }

    private fun check(result: MethodChannel.Result) {
        val id = begin("check", result)
        submit(id) {
            // The serial worker never creates a second partial until its previous transfer exits.
            app.cacheDir.listFiles()?.filter {
                it.name.startsWith("official-apk-") && it.name.endsWith(".apk") &&
                    it.lastModified() < System.currentTimeMillis() - 24 * 60 * 60_000L
            }?.forEach { it.delete() }
            val r = fromMirrors(policy.manifests) { readManifest(it) }
            active(id)
            val newer = r.code > code(currentInfo())
            val target = verifiedFile(r)
            if (!newer) discardOtherPackages(null)
            val cached = newer && target.isFile && try {
                verifyCached(r, id); true
            } catch (e: UpdateFailure) {
                if (e.code == "cancelled") throw e
                target.delete(); false
            }
            handler.post {
                if (id == epoch && !closed) {
                    selection = r; permissionRequested = false
                    state = if (!newer) "current" else if (cached) "ready" else "available"
                    if (cached) received = r.size
                    complete()
                }
            }
        }
    }

    private fun readManifest(uri: URI): OfficialRelease = request(uri) { connection ->
        if (connection.contentLengthLong > OfficialUpdatePolicy.MAX_MANIFEST) throw UpdateFailure("invalid_release")
        val raw = ByteArrayOutputStream()
        val deadline = SystemClock.elapsedRealtime() + 20_000
        connection.inputStream.use { input ->
            val buf = ByteArray(4096)
            while (true) {
                val n = input.read(buf)
                if (n < 0) break
                if (SystemClock.elapsedRealtime() >= deadline) throw IOException("timeout")
                if (raw.size() + n > OfficialUpdatePolicy.MAX_MANIFEST) throw UpdateFailure("invalid_release")
                raw.write(buf, 0, n)
            }
        }
        val row = try { JSONObject(raw.toString("UTF-8")) } catch (_: Exception) { throw UpdateFailure("invalid_release") }
        fun string(key: String) = row.opt(key) as? String ?: throw UpdateFailure("invalid_release")
        fun number(key: String): Long = when (val v = row.opt(key)) {
            is Long -> v; is Int -> v.toLong(); else -> throw UpdateFailure("invalid_release")
        }
        policy.release(app.packageName, string("package"), string("slug"), number("versionCode"), string("versionName"),
            number("bytes"), string("sha256"), string("url"), if (row.has("urlFallback")) string("urlFallback") else null)
    }

    private fun download(result: MethodChannel.Result) {
        val r = selection ?: throw UpdateFailure("not_ready")
        if (r.code <= code(currentInfo())) { state = "current"; result.success(snapshot()); return }
        if (state == "ready" && verifiedFile(r).isFile) { result.success(snapshot()); return }
        val id = begin("download", result)
        submit(id) {
            var temp: File? = null
            try {
                temp = try { File.createTempFile("official-apk-", ".apk", app.cacheDir) }
                    catch (_: IOException) { throw UpdateFailure("storage") }
                val part = temp
                fromMirrors(r.mirrors, retryBadBytes = true) { uri ->
                    active(id); received = 0
                    val deadline = SystemClock.elapsedRealtime() + 20 * 60_000L
                    request(uri) { c ->
                        val length = c.contentLengthLong
                        if (length >= 0 && length != r.size) throw UpdateFailure("verification")
                        val stream = try { part.outputStream() } catch (_: IOException) { throw UpdateFailure("storage") }
                        stream.use { output ->
                            c.inputStream.use { input ->
                                policy.verifyBytes(input, output, r) { size ->
                                    active(id)
                                    if (SystemClock.elapsedRealtime() >= deadline) throw IOException("timeout")
                                    received = size
                                }
                            }
                        }
                    }
                }
                active(id); verifying = true
                verifyIdentity(part, r)
                active(id)
                handler.post {
                    try {
                        if (id != epoch || closed) return@post
                        if (!cache.isDirectory && !cache.mkdirs()) throw UpdateFailure("storage")
                        if (!part.renameTo(verifiedFile(r))) throw UpdateFailure("storage")
                        state = "ready"; received = r.size
                        discardOtherPackages(verifiedFile(r))
                        complete()
                    } catch (e: Exception) {
                        if (id == epoch && !closed) completeError(if (e is UpdateFailure) e.code else "storage")
                    } finally { part.delete() }
                }
                temp = null // The main looper now owns this particular verified file.
            } finally { temp?.delete() }
        }
    }

    private fun discardOtherPackages(keep: File?) {
        cache.listFiles()?.filter { it != keep && it.name.matches(Regex("[a-f0-9]{64}\\.apk")) }?.forEach { it.delete() }
    }

    private fun verifiedFile(r: OfficialRelease) = File(cache, r.sha + ".apk")

    private fun verifyCached(r: OfficialRelease, id: Long) {
        val f = verifiedFile(r)
        if (!f.isFile || f.length() != r.size) throw UpdateFailure("verification")
        f.inputStream().use { stream -> policy.verifyBytes(stream, null, r) { active(id) } }
        verifyIdentity(f, r)
    }

    @Suppress("DEPRECATION")
    private fun verifyIdentity(f: File, r: OfficialRelease) {
        val flags = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
        val apk = pm.getPackageArchiveInfo(f.absolutePath, flags) ?: throw UpdateFailure("verification")
        val installed = pm.getPackageInfo(app.packageName, flags)
        if (!policy.validIdentity(app.packageName, code(installed), apk.packageName, code(apk), apk.versionName, r)) {
            throw UpdateFailure("verification")
        }
        fun signers(p: PackageInfo): Set<String> {
            val values = if (Build.VERSION.SDK_INT >= 28) p.signingInfo?.apkContentsSigners else p.signatures
            return values.orEmpty().map { signature ->
                val digest = MessageDigest.getInstance("SHA-256").digest(signature.toByteArray())
                android.util.Base64.encodeToString(digest, android.util.Base64.NO_WRAP)
            }.toSet()
        }
        if (!policy.sameSigners(signers(installed), signers(apk))) throw UpdateFailure("verification")
    }

    private fun install(result: MethodChannel.Result) {
        val r = selection ?: throw UpdateFailure("not_ready")
        if (installerOpen) { result.success(snapshot("launched")); return }
        if (state != "ready" || !verifiedFile(r).isFile) throw UpdateFailure("not_ready")
        if (!pm.canRequestPackageInstalls()) {
            permissionRequested = true; result.success(snapshot("permission_required")); return
        }
        val id = begin("install", result)
        submit(id) {
            try { verifyCached(r, id) } catch (e: UpdateFailure) {
                if (e.code == "verification") handler.post {
                    if (id == epoch && !closed) { verifiedFile(r).delete(); state = "available" }
                }
                throw e
            }
            handler.post {
                if (id != epoch || closed) return@post
                if (!foreground || activity.isFinishing || activity.isDestroyed) { completeError("foreground"); return@post }
                if (!pm.canRequestPackageInstalls()) { permissionRequested = true; complete("permission_required"); return@post }
                try {
                    val uri = FileProvider.getUriForFile(app, app.packageName + ".verifiedupdates", verifiedFile(r))
                    activity.startActivity(systemInstaller(uri))
                    installerOpen = true; permissionRequested = false; complete("launched")
                } catch (_: Exception) { completeError("installer_unavailable") }
            }
        }
    }

    @Suppress("DEPRECATION")
    private fun systemInstaller(uri: Uri): Intent {
        // Prefer the system install action. Some OEM installers only register the APK view action.
        val flags = PackageManager.MATCH_DEFAULT_ONLY or PackageManager.MATCH_SYSTEM_ONLY
        for (action in listOf(Intent.ACTION_INSTALL_PACKAGE, Intent.ACTION_VIEW)) {
            val intent = Intent(action).setDataAndType(uri, "application/vnd.android.package-archive")
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            val candidates = pm.queryIntentActivities(intent, flags).map { it.activityInfo }.filter {
                it.exported && (it.applicationInfo.flags and
                    (ApplicationInfo.FLAG_SYSTEM or ApplicationInfo.FLAG_UPDATED_SYSTEM_APP)) != 0
            }
            val default = pm.resolveActivity(intent, flags)?.activityInfo
            val chosen = candidates.firstOrNull { it.packageName == default?.packageName && it.name == default.name }
                ?: candidates.singleOrNull()
                ?: candidates.firstOrNull { pm.checkPermission(android.Manifest.permission.INSTALL_PACKAGES,
                    it.packageName) == PackageManager.PERMISSION_GRANTED }
                ?: continue
            intent.component = ComponentName(chosen.packageName, chosen.name)
            intent.clipData = ClipData.newRawUri("APK", uri)
            return intent
        }
        throw UpdateFailure("installer_unavailable")
    }

    private fun openSettings(result: MethodChannel.Result) {
        if (!permissionRequested || state != "ready") throw UpdateFailure("not_ready")
        if (pm.canRequestPackageInstalls()) { result.success(snapshot("ready")); return }
        try {
            activity.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + app.packageName)))
            result.success(snapshot("settings_opened"))
        } catch (_: Exception) { throw UpdateFailure("installer_unavailable") }
    }

    private fun <T> fromMirrors(mirrors: List<URI>, retryBadBytes: Boolean = false, read: (URI) -> T): T {
        var badBytes = false
        for (uri in mirrors) {
            try {
                return read(uri)
            } catch (e: UpdateFailure) {
                if (!retryBadBytes || e.code != "verification") throw e
                badBytes = true
            } catch (_: IOException) {
                // The approved mirror receives an independent, fully verified request.
            }
        }
        throw UpdateFailure(if (badBytes) "verification" else "network")
    }

    private fun <T> request(uri: URI, read: (HttpsURLConnection) -> T): T {
        val connection = uri.toURL().openConnection() as HttpsURLConnection
        try {
            connection.instanceFollowRedirects = false
            connection.connectTimeout = 8_000; connection.readTimeout = 20_000
            connection.useCaches = false
            connection.setRequestProperty("Accept-Encoding", "identity")
            if (connection.responseCode != 200) throw IOException("http")
            return read(connection)
        } finally { connection.disconnect() }
    }
}
