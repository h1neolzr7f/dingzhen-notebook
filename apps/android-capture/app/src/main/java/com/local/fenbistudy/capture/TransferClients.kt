package com.local.fenbistudy.capture

import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/** Copy frames to a user-selected folder; existing checksums make it resumable. */
class UsbTransferClient(private val destination: File) : TransferClient {
    override fun transfer(task: CaptureTask, state: CaptureSessionState): CaptureSessionState {
        var transferred = state.lastTransferredSequence
        state.savedPaths.forEachIndexed { index, sourcePath ->
            val sequence = index.toLong()
            if (sequence <= transferred) return@forEachIndexed
            val source = File(sourcePath)
            if (!source.exists()) return@forEachIndexed
            val target = File(destination, "${task.id}/${source.name}").apply { parentFile?.mkdirs() }
            if (!target.exists() || sha256(target) != state.checksums[sequence]) source.copyTo(target, overwrite = true)
            if (sha256(target) == state.checksums[sequence]) transferred = sequence
        }
        return state.copy(lastTransferredSequence = transferred)
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
            while (true) { val n = input.read(buffer); if (n <= 0) break; digest.update(buffer, 0, n) }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}

/** LAN transport uses HMAC-authenticated POSTs and resumes only after a verified acknowledgement. */
class LanTransferClient(
    private val endpoint: URL,
    secret: ByteArray,
    private val connectTimeoutMs: Int = 5000,
    private val nowEpochSeconds: () -> Long = { System.currentTimeMillis() / 1000L },
) : TransferClient {
    private val signer = LanRequestSigner(secret)

    init {
        require(isSecureTransferEndpoint(endpoint)) {
            "LAN endpoint must use HTTPS (plain HTTP is allowed only on loopback)"
        }
    }

    override fun transfer(task: CaptureTask, state: CaptureSessionState): CaptureSessionState {
        var transferred = state.lastTransferredSequence
        state.savedPaths.forEachIndexed { index, sourcePath ->
            val sequence = index.toLong()
            if (sequence <= transferred) return@forEachIndexed
            val file = File(sourcePath)
            if (!file.exists()) return@forEachIndexed
            val path = "/capture/${task.id}/$sequence"
            val timestamp = nowEpochSeconds()
            val checksum = state.checksums[sequence] ?: return@forEachIndexed
            val connection = (URL(endpoint, path).openConnection() as HttpURLConnection)
            connection.requestMethod = "POST"
            connection.connectTimeout = connectTimeoutMs
            connection.readTimeout = connectTimeoutMs
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "image/png")
            connection.setRequestProperty("X-Checksum-SHA256", checksum)
            connection.setRequestProperty("X-Fenbi-Timestamp", timestamp.toString())
            connection.setRequestProperty("X-Fenbi-Signature", signer.sign("POST", path, timestamp, checksum))
            runCatching {
                connection.outputStream.use { output -> file.inputStream().use { input -> input.copyTo(output) } }
                if (connection.responseCode in 200..299 && connection.getHeaderField("X-Checksum-SHA256") == checksum) {
                    transferred = sequence
                }
            }
            connection.disconnect()
        }
        if (state.savedPaths.isNotEmpty() && transferred >= (state.savedPaths.size - 1).toLong()) {
            complete(task)
        }
        return state.copy(lastTransferredSequence = transferred)
    }

    private fun complete(task: CaptureTask) {
        val path = "/capture/${task.id}/complete"
        val timestamp = nowEpochSeconds()
        val checksum = EMPTY_SHA256
        val connection = (URL(endpoint, path).openConnection() as HttpURLConnection)
        connection.requestMethod = "POST"
        connection.connectTimeout = connectTimeoutMs
        connection.readTimeout = connectTimeoutMs
        connection.doOutput = true
        connection.setRequestProperty("Content-Type", "application/json")
        connection.setRequestProperty("Content-Length", "0")
        connection.setRequestProperty("X-Checksum-SHA256", checksum)
        connection.setRequestProperty("X-Fenbi-Timestamp", timestamp.toString())
        connection.setRequestProperty("X-Fenbi-Signature", signer.sign("POST", path, timestamp, checksum))
        runCatching { connection.outputStream.use { } }
        connection.disconnect()
    }

    companion object {
        const val EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    }
}
