package com.local.fenbistudy.capture

enum class FrameRejection {
    ACCEPTED,
    PAUSED,
    STOPPED,
    TOO_SOON,
    DUPLICATE,
    MANUAL_NOT_REQUESTED,
}

data class FrameAdmission(
    val reason: FrameRejection,
    val duplicateStreak: Int = 0,
) {
    val accepted: Boolean get() = reason == FrameRejection.ACCEPTED
}

/** Thread-safe admission gate shared by MediaProjection callbacks and controls. */
class FrameAdmissionPolicy(
    private val minIntervalMs: Long = 900,
    private val duplicateDistance: Int = 2,
) {
    private var active = false
    private var paused = false
    private var mode = CaptureMode.SEMI_AUTO
    private var manualRequested = false
    private var lastAcceptedAt = Long.MIN_VALUE
    private var lastSignature: Long? = null
    private var duplicateStreak = 0

    @Synchronized
    fun start(nextMode: CaptureMode) {
        active = true
        paused = false
        mode = nextMode
        manualRequested = false
        lastAcceptedAt = Long.MIN_VALUE
        lastSignature = null
        duplicateStreak = 0
    }

    @Synchronized fun pause() { paused = true }
    @Synchronized fun resume() { if (active) paused = false }
    @Synchronized fun stop() { active = false; paused = false; manualRequested = false }
    @Synchronized fun requestManualFrame() { if (active && !paused) manualRequested = true }

    @Synchronized
    fun mayDecode(): Boolean = active && !paused && (mode != CaptureMode.MANUAL || manualRequested)

    @Synchronized
    fun evaluate(nowMs: Long, signature: Long): FrameAdmission {
        if (!active) return FrameAdmission(FrameRejection.STOPPED, duplicateStreak)
        if (paused) return FrameAdmission(FrameRejection.PAUSED, duplicateStreak)
        if (mode == CaptureMode.MANUAL && !manualRequested) {
            return FrameAdmission(FrameRejection.MANUAL_NOT_REQUESTED, duplicateStreak)
        }
        if (lastAcceptedAt != Long.MIN_VALUE && nowMs - lastAcceptedAt < minIntervalMs) {
            return FrameAdmission(FrameRejection.TOO_SOON, duplicateStreak)
        }
        val previous = lastSignature
        if (previous != null && java.lang.Long.bitCount(previous xor signature) <= duplicateDistance) {
            duplicateStreak += 1
            return FrameAdmission(FrameRejection.DUPLICATE, duplicateStreak)
        }
        lastAcceptedAt = nowMs
        lastSignature = signature
        duplicateStreak = 0
        manualRequested = false
        return FrameAdmission(FrameRejection.ACCEPTED)
    }
}
