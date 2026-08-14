package com.local.fenbistudy.capture

import java.net.URL
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

class LanRequestSigner(secret: ByteArray) {
    private val key = secret.copyOf().also { require(it.size >= 16) { "LAN secret must be at least 16 bytes" } }

    fun sign(method: String, path: String, timestamp: Long, checksum: String): String {
        val message = "${method.uppercase()}\n$path\n$timestamp\n$checksum".toByteArray(Charsets.UTF_8)
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(key, "HmacSHA256"))
        return mac.doFinal(message).joinToString("") { "%02x".format(it) }
    }

    fun verify(signature: String, method: String, path: String, timestamp: Long, checksum: String): Boolean {
        val expected = sign(method, path, timestamp, checksum).toByteArray(Charsets.US_ASCII)
        return java.security.MessageDigest.isEqual(expected, signature.lowercase().toByteArray(Charsets.US_ASCII))
    }
}

fun isPrivateLanHost(host: String): Boolean {
    val value = host.trim().lowercase().trim('[', ']')
    if (value in setOf("127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1")) return true
    val parts = value.split('.')
    if (parts.size != 4) return false
    val octets = parts.map { it.toIntOrNull() ?: return false }
    if (octets.any { it !in 0..255 }) return false
    val a = octets[0]
    val b = octets[1]
    return a == 10 || (a == 172 && b in 16..31) || (a == 192 && b == 168) || (a == 169 && b == 254)
}

fun isSecureTransferEndpoint(endpoint: URL): Boolean {
    if (endpoint.protocol.equals("https", ignoreCase = true)) return true
    if (!endpoint.protocol.equals("http", ignoreCase = true)) return false
    return isPrivateLanHost(endpoint.host)
}

fun parsePairingCode(raw: String): Pair<URL, ByteArray>? {
    val text = raw.trim()
    if (!text.startsWith("FENBI1|")) return null
    val parts = text.split("|", limit = 3)
    if (parts.size != 3) return null
    val endpoint = runCatching { URL(parts[1]) }.getOrNull() ?: return null
    val secret = parts[2].toByteArray(Charsets.UTF_8)
    if (secret.size < 16 || !isSecureTransferEndpoint(endpoint)) return null
    return endpoint to secret
}
