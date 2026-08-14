package com.local.fenbistudy.capture

/**
 * Small explicit mode state machine used by the UI/service boundary.  It
 * makes the AUTO -> SEMI_AUTO safety fallback testable without a device.
 */
class CaptureModeController(initial: CaptureMode = CaptureMode.SEMI_AUTO) {
    var mode: CaptureMode = initial
        private set

    fun select(next: CaptureMode) {
        mode = next
    }

    fun onAutomaticFailure(): CaptureMode {
        if (mode == CaptureMode.AUTO) mode = CaptureMode.SEMI_AUTO
        return mode
    }
}
