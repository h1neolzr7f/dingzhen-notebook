package com.local.fenbistudy.capture

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FenbiAppGuardTest {
    @Test
    fun onlyOfficialFenbiPackagesAreAccepted() {
        assertTrue(FenbiAppGuard.isFenbi("com.fenbi.android.servant"))
        assertTrue(FenbiAppGuard.isFenbi("com.fenbi"))
        assertFalse(FenbiAppGuard.isFenbi("com.tencent.mm"))
        assertFalse(FenbiAppGuard.isFenbi(null))
        assertTrue(FenbiAppGuard.KNOWN_PACKAGES.all(FenbiAppGuard::isFenbi))
    }

    @Test
    fun neverTreatsYuanTiKuOrXiaoYuanAsFenbi() {
        assertFalse(FenbiAppGuard.isFenbi("com.fenbi.android.solar"))
        assertFalse(FenbiAppGuard.isFenbi("com.fenbi.android.leo"))
        assertFalse(FenbiAppGuard.isFenbi("com.yuantiku.android"))
        assertFalse(FenbiAppGuard.KNOWN_PACKAGES.contains("com.fenbi.android.solar"))
    }

    @Test
    fun prefersChalkAppWhenBothInstalled() {
        assertEquals(
            "com.fenbi.android.servant",
            FenbiAppGuard.pickLaunchPackage(listOf("com.fenbi.android.solar", "com.fenbi.android.servant")),
        )
        assertEquals(null, FenbiAppGuard.pickLaunchPackage(listOf("com.fenbi.android.solar", "com.yuantiku.android")))
    }
}
