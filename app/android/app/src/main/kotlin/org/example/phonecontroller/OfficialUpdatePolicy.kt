package org.example.phonecontroller

import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.net.URI
import java.security.MessageDigest

internal class UpdateFailure(val code: String) : Exception(code)

internal data class OfficialRelease(
    val code: Long, val name: String, val size: Long, val sha: String, val mirrors: List<URI>
)

/** The signed build's official store page fixes the DNS zone; metadata can never add a host. */
internal class OfficialUpdatePolicy(configuredPage: String) {
    companion object {
        const val SLUG = "phone-controller-flash"
        const val MAX_APK = 256L * 1024 * 1024
        const val MAX_MANIFEST = 64 * 1024
        private val version = Regex("[0-9]{1,5}(?:\\.[0-9]{1,5}){1,3}")
        private val filename = Regex("phone-controller-[A-Za-z0-9][A-Za-z0-9._-]{0,150}\\.apk")
        private val hash = Regex("[a-f0-9]{64}")
    }

    private val hosts: List<String>
    val manifests: List<URI>

    init {
        val page = runCatching { URI(configuredPage) }.getOrNull()
            ?: throw UpdateFailure("invalid_release")
        val host = page.host.orEmpty().lowercase(java.util.Locale.ROOT)
        if (!plainHttps(page) || host.substringBefore('.') !in setOf("d", "cdn") ||
            !host.substringAfter('.', "").contains('.') ||
            page.rawPath !in setOf("/apps/$SLUG", "/apps/$SLUG/", "/apps/$SLUG/index.html"))
            throw UpdateFailure("invalid_release")
        val zone = host.substringAfter('.')
        hosts = listOf("d.$zone", "cdn.$zone")
        manifests = hosts.map { URI("https://$it/apps/$SLUG/latest.json") }
    }

    private fun plainHttps(u: URI) = u.scheme == "https" && u.host != null && u.port == -1 &&
        u.rawUserInfo == null && u.rawQuery == null && u.rawFragment == null

    fun release(expectedPackage: String, rowPackage: String, slug: String, code: Long, name: String,
                bytes: Long, sha: String, primary: String, fallback: String?): OfficialRelease {
        if (slug != SLUG || expectedPackage != rowPackage || code !in 1..Int.MAX_VALUE.toLong() ||
            !version.matches(name) || bytes !in 1..MAX_APK || !hash.matches(sha))
            throw UpdateFailure("invalid_release")
        val prefix = "/apps/$SLUG/releases/$name/"
        val mirrors = listOfNotNull(primary, fallback).distinct().map {
            val u = runCatching { URI(it) }.getOrNull() ?: throw UpdateFailure("invalid_release")
            if (!plainHttps(u) || u.host !in hosts || !u.rawPath.startsWith(prefix) ||
                !filename.matches(u.rawPath.removePrefix(prefix))) throw UpdateFailure("invalid_release")
            u
        }
        return OfficialRelease(code, name, bytes, sha, mirrors)
    }

    fun verifyBytes(input: InputStream, output: OutputStream?, release: OfficialRelease, progress: (Long) -> Unit) {
        var count = 0L
        val digest = MessageDigest.getInstance("SHA-256")
        val buffer = ByteArray(64 * 1024)
        while (true) {
            val n = input.read(buffer)
            if (n < 0) break
            count += n
            if (count > release.size) throw UpdateFailure("verification")
            progress(count)
            try { output?.write(buffer, 0, n) } catch (_: IOException) { throw UpdateFailure("storage") }
            digest.update(buffer, 0, n)
        }
        val got = digest.digest().joinToString("") { "%02x".format(it) }
        if (count != release.size || got != release.sha) throw UpdateFailure("verification")
    }

    fun validIdentity(installedPackage: String, installedCode: Long, apkPackage: String, apkCode: Long,
                      apkName: String?, release: OfficialRelease) =
        installedPackage == apkPackage && installedCode < release.code && apkCode == release.code && apkName == release.name

    fun sameSigners(installed: Set<String>, candidate: Set<String>) =
        installed.isNotEmpty() && installed == candidate
}
