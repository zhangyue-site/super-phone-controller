package org.example.phonecontroller

import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.OutputStream
import java.net.URI
import java.security.MessageDigest

fun main() {
    val base = "https://d.example.test/apps/phone-controller-flash/"
    fun withUserInfo(host: String, userInfo: String, path: String) =
        URI("https", userInfo, host, -1, path, null, null).toASCIIString()
    val mirror = base.replace("d.example", "cdn.example")
    val policy = OfficialUpdatePolicy(base)
    val body = "signed APK test fixture".toByteArray()
    val sha = MessageDigest.getInstance("SHA-256").digest(body).joinToString("") { "%02x".format(it) }
    val file = "releases/1.4.18/phone-controller-site-1.4.18-vc98.apk"
    val pkg = "test.app"
    fun release(
        url: String = mirror + file, backup: String? = base + file, slug: String = OfficialUpdatePolicy.SLUG,
        rowPackage: String = pkg, code: Long = 98, name: String = "1.4.18",
        size: Long = body.size.toLong(), digest: String = sha
    ) = policy.release(pkg, rowPackage, slug, code, name, size, digest, url, backup)
    var passed = 0
    fun expect(test: Boolean) { check(test); passed++ }
    fun rejects(reason: String, work: () -> Unit) {
        val error = runCatching(work).exceptionOrNull()
        check(error is UpdateFailure && error.code == reason) { "Expected $reason, got $error" }
        passed++
    }
    expect(policy.manifests.map { it.toASCIIString() } == listOf(base + "latest.json", mirror + "latest.json"))
    expect(OfficialUpdatePolicy(mirror + "index.html").manifests == policy.manifests)
    listOf("http://d.example.test/apps/phone-controller-flash/", base + "?preview=1", base + "#other",
        "https://admin.example.test/apps/phone-controller-flash/", "https://d.example.test/apps/another/",
        withUserInfo("d.example.test", "login", "/apps/phone-controller-flash/")).forEach { bad ->
        rejects("invalid_release") { OfficialUpdatePolicy(bad) }
    }
    val r = release()
    expect(r.code == 98L && r.mirrors.size == 2 && r.mirrors[0].toASCIIString() == mirror + file)
    expect(release(backup = null).mirrors.size == 1)
    expect(release(url = base + file).mirrors.size == 1)
    listOf(
        "http://d.example.test/apps/phone-controller-flash/$file",
        "https://d.example.test.evil.test/apps/phone-controller-flash/$file",
        withUserInfo("evil.test", "d.example.test", "/apps/phone-controller-flash/$file"),
        withUserInfo("d.example.test", "user", "/apps/phone-controller-flash/$file"),
        "https://d.example.test:8443/apps/phone-controller-flash/$file",
        base + file + "?signed=0", base + file + "#download", base + file.replace("1.4.18/", "1.4.17/"),
        base + file.replace("phone-controller-site", "..%2Fphone-controller-site"),
        base + file.replace("phone-controller-site", "../phone-controller-site"),
        base + file.replace("phone-controller-site", "other-product"),
        base + file.replace("phone-controller-site", "nested/phone-controller-site"),
        base + file.replace(".apk", ".zip"),
        base.replace("phone-controller-flash", "other") + file
    ).forEach { bad -> rejects("invalid_release") { release(url = bad) } }
    rejects("invalid_release") { release(backup = "https://evil.test/$file") }
    rejects("invalid_release") { release(slug = "other") }
    rejects("invalid_release") { release(rowPackage = "wrong.package") }
    rejects("invalid_release") { release(code = 0) }
    rejects("invalid_release") { release(name = "../1.4.18") }
    rejects("invalid_release") { release(size = 0) }
    rejects("invalid_release") { release(size = OfficialUpdatePolicy.MAX_APK + 1) }
    rejects("invalid_release") { release(digest = "bad") }
    val sink = ByteArrayOutputStream()
    var received = 0L
    policy.verifyBytes(body.inputStream(), sink, r) { received = it }
    expect(sink.toByteArray().contentEquals(body) && received == r.size)
    rejects("verification") { policy.verifyBytes(body.drop(1).toByteArray().inputStream(), null, r) {} }
    rejects("verification") { policy.verifyBytes((body + 42.toByte()).inputStream(), null, r) {} }
    rejects("verification") { policy.verifyBytes(ByteArray(body.size).inputStream(), null, r) {} }
    rejects("cancelled") { policy.verifyBytes(body.inputStream(), null, r) { throw UpdateFailure("cancelled") } }
    rejects("storage") {
        val full = object : OutputStream() { override fun write(b: Int) { throw IOException("no space") } }
        policy.verifyBytes(body.inputStream(), full, r) {}
    }
    expect(policy.validIdentity(pkg, 97, pkg, 98, "1.4.18", r))
    expect(!policy.validIdentity(pkg, 98, pkg, 98, "1.4.18", r))
    expect(!policy.validIdentity(pkg, 99, pkg, 98, "1.4.18", r))
    expect(!policy.validIdentity(pkg, 97, "other", 98, "1.4.18", r))
    expect(!policy.validIdentity(pkg, 97, pkg, 99, "1.4.18", r))
    expect(!policy.validIdentity(pkg, 97, pkg, 98, "1.4.19", r))
    expect(policy.sameSigners(setOf("a"), setOf("a")))
    expect(policy.sameSigners(setOf("a", "b"), setOf("b", "a")))
    expect(!policy.sameSigners(setOf("a", "b"), setOf("a")))
    expect(!policy.sameSigners(setOf("a"), setOf("other")))
    expect(!policy.sameSigners(emptySet(), emptySet()))
    println("official Android update policy: $passed checks passed")
}
