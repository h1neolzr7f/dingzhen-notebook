package com.local.fenbistudy.capture

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FrameAdmissionPolicyTest {
    @Test
    fun pausedAndStoppedSessionsRejectFrames() {
        val policy = FrameAdmissionPolicy(minIntervalMs = 500, duplicateDistance = 0)
        policy.start(CaptureMode.SEMI_AUTO)
        assertTrue(policy.evaluate(1_000, 1L).accepted)
        policy.pause()
        assertEquals(FrameRejection.PAUSED, policy.evaluate(2_000, 2L).reason)
        policy.resume()
        assertTrue(policy.evaluate(2_000, 2L).accepted)
        policy.stop()
        assertEquals(FrameRejection.STOPPED, policy.evaluate(3_000, 3L).reason)
    }

    @Test
    fun throttlesAndRejectsDuplicateFrames() {
        val policy = FrameAdmissionPolicy(minIntervalMs = 500, duplicateDistance = 1)
        policy.start(CaptureMode.AUTO)
        assertTrue(policy.evaluate(1_000, 0b1111L).accepted)
        assertEquals(FrameRejection.TOO_SOON, policy.evaluate(1_100, 0b0000L).reason)
        val duplicate = policy.evaluate(1_600, 0b1110L)
        assertEquals(FrameRejection.DUPLICATE, duplicate.reason)
        assertEquals(1, duplicate.duplicateStreak)
        assertTrue(policy.evaluate(2_200, 0b0000L).accepted)
    }

    @Test
    fun manualModeRequiresAnExplicitRequest() {
        val policy = FrameAdmissionPolicy(minIntervalMs = 0, duplicateDistance = 0)
        policy.start(CaptureMode.MANUAL)
        assertEquals(FrameRejection.MANUAL_NOT_REQUESTED, policy.evaluate(1_000, 1L).reason)
        policy.requestManualFrame()
        assertTrue(policy.evaluate(1_001, 1L).accepted)
        assertFalse(policy.evaluate(1_002, 2L).accepted)
    }
}
