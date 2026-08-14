package com.local.fenbistudy.capture

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.SystemClock
import android.util.DisplayMetrics
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest

/**
 * Raw screenshot capture using Android's user-consented MediaProjection API.
 * It never drives taps or swipes; AUTO mode is only a pacing hint and falls
 * back to SEMI_AUTO when a frame cannot be acquired.
 */
class MediaProjectionCapture(
    private val context: Context,
    private val store: CaptureTaskStore,
    private val onFailure: (String) -> Unit = {},
) {
    companion object {
        const val EXTRA_RESULT_CODE = "projection_result_code"
        const val EXTRA_RESULT_DATA = "projection_result_data"
        const val EXTRA_TASK_ID = "capture_task_id"
        const val EXTRA_MODE = "capture_mode"
    }

    private var projection: MediaProjection? = null
    private var reader: ImageReader? = null
    private var virtualDisplay: android.hardware.display.VirtualDisplay? = null
    private var task: CaptureTask? = null
    private var state: CaptureSessionState? = null
    private var frameWidth = 0
    private var frameHeight = 0
    private var densityDpi = 0
    private val thread = HandlerThread("fenbi-capture").also { it.start() }
    private val handler = Handler(thread.looper)
    private val admission = FrameAdmissionPolicy()

    fun start(resultCode: Int, resultData: Intent, captureTask: CaptureTask): Boolean {
        return runCatching {
            val manager = context.getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            projection = manager.getMediaProjection(resultCode, resultData)
                ?: error("MediaProjection permission was not granted")
            task = captureTask
            admission.start(captureTask.mode)
            val metrics = DisplayMetrics()
            @Suppress("DEPRECATION")
            (context.getSystemService(Context.WINDOW_SERVICE) as android.view.WindowManager)
                .defaultDisplay.getRealMetrics(metrics)
            frameWidth = metrics.widthPixels
            frameHeight = metrics.heightPixels
            densityDpi = metrics.densityDpi
            reader = ImageReader.newInstance(frameWidth, frameHeight, PixelFormat.RGBA_8888, 2)
            reader?.setOnImageAvailableListener({ imageReader -> onImage(imageReader) }, handler)
            virtualDisplay = projection?.createVirtualDisplay(
                "FenbiCapture",
                frameWidth,
                frameHeight,
                densityDpi,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                reader?.surface,
                null,
                handler,
            )
            val current = store.loadSession(captureTask.id)
            state = (current ?: CaptureSessionState(captureTask.id, CaptureTaskStatus.CREATED, -1, emptyList(), emptyMap()))
                .copy(status = CaptureTaskStatus.RUNNING)
            store.saveSession(state!!)
        }.onFailure { error -> onFailure(error.message ?: "capture start failed") }.isSuccess
    }

    private fun onImage(imageReader: ImageReader) {
        val image = runCatching { imageReader.acquireLatestImage() }.getOrNull() ?: return
        try {
            if (!admission.mayDecode()) return
            val captureTask = task ?: return
            val current = state ?: return
            val bitmap = imageToBitmap(image) ?: return
            val decision = admission.evaluate(SystemClock.elapsedRealtime(), averageHash(bitmap))
            if (!decision.accepted) {
                bitmap.recycle()
                if (captureTask.mode == CaptureMode.AUTO && decision.duplicateStreak >= 3) {
                    pauseWithError("页面连续三次未变化，已安全暂停")
                }
                return
            }
            val next = current.lastSequence + 1
            val directory = File(captureTask.outputDirectory).apply { mkdirs() }
            val output = File(directory, "%06d.png".format(next))
            FileOutputStream(output).use { stream -> bitmap.compress(Bitmap.CompressFormat.PNG, 100, stream) }
            val checksum = sha256(output)
            state = current.copy(
                lastSequence = next,
                savedPaths = current.savedPaths + output.absolutePath,
                checksums = current.checksums + (next to checksum),
                status = CaptureTaskStatus.RUNNING,
            )
            store.saveSession(state!!)
            bitmap.recycle()
        } catch (error: Throwable) {
            onFailure(error.message ?: "frame save failed")
            val current = state
            if (current != null) {
                state = current.copy(status = CaptureTaskStatus.FALLBACK_SEMI_AUTO, errorMessage = error.message)
                store.saveSession(state!!)
            }
        } finally {
            image.close()
        }
    }

    private fun imageToBitmap(image: Image): Bitmap? {
        val plane = image.planes.firstOrNull() ?: return null
        val buffer = plane.buffer
        val pixelStride = plane.pixelStride
        val rowStride = plane.rowStride
        val rowPadding = rowStride - pixelStride * image.width
        val paddedWidth = image.width + rowPadding / pixelStride
        val bitmap = Bitmap.createBitmap(paddedWidth, image.height, Bitmap.Config.ARGB_8888)
        bitmap.copyPixelsFromBuffer(buffer)
        return Bitmap.createBitmap(bitmap, 0, 0, image.width, image.height).also { bitmap.recycle() }
    }

    fun pause() {
        admission.pause()
        state?.let { state = it.copy(status = CaptureTaskStatus.PAUSED); store.saveSession(state!!) }
    }

    fun resume() {
        admission.resume()
        state?.let { state = it.copy(status = CaptureTaskStatus.RUNNING); store.saveSession(state!!) }
    }

    fun requestFrame() = admission.requestManualFrame()

    private fun pauseWithError(message: String) {
        admission.pause()
        state?.let {
            state = it.copy(status = CaptureTaskStatus.PAUSED, errorMessage = message)
            store.saveSession(state!!)
        }
        onFailure(message)
    }

    fun stop(status: CaptureTaskStatus = CaptureTaskStatus.STOPPED) {
        admission.stop()
        state?.let { state = it.copy(status = status); store.saveSession(state!!) }
        virtualDisplay?.release()
        reader?.close()
        projection?.stop()
        virtualDisplay = null
        reader = null
        projection = null
    }

    private fun averageHash(bitmap: Bitmap): Long {
        val scaled = Bitmap.createScaledBitmap(bitmap, 8, 8, true)
        val values = IntArray(64)
        var sum = 0L
        for (y in 0 until 8) for (x in 0 until 8) {
            val pixel = scaled.getPixel(x, y)
            val luminance = (android.graphics.Color.red(pixel) * 299 +
                android.graphics.Color.green(pixel) * 587 + android.graphics.Color.blue(pixel) * 114) / 1000
            values[y * 8 + x] = luminance
            sum += luminance
        }
        if (scaled !== bitmap) scaled.recycle()
        val average = sum / values.size
        var signature = 0L
        values.forEachIndexed { index, value -> if (value >= average) signature = signature or (1L shl index) }
        return signature
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
            while (true) {
                val count = input.read(buffer)
                if (count <= 0) break
                digest.update(buffer, 0, count)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}
