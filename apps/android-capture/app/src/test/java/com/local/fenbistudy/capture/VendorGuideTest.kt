package com.local.fenbistudy.capture

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class VendorGuideTest {
    @Test
    fun xiaomiFamilyCoversRedmiPoco() {
        assertEquals(VendorFamily.XIAOMI, VendorGuide.family("Xiaomi", "Redmi"))
        assertEquals(VendorFamily.XIAOMI, VendorGuide.family("xiaomi", "poco"))
        assertEquals(VendorFamily.XIAOMI, VendorGuide.family("Qualcomm", "Xiaomi", "HyperOS"))
        assertEquals(VendorFamily.OTHER, VendorGuide.family("Google", "pixel"))
    }

    @Test
    fun xiaomiStepsPointToDownloadedServices() {
        val steps = VendorGuide.steps(VendorFamily.XIAOMI).joinToString()
        assertTrue(steps.contains("已下载的服务"))
        assertTrue(VendorGuide.title(VendorFamily.XIAOMI).contains("点一下"))
        assertEquals("丁真自动翻页", VendorGuide.SERVICE_LABEL)
        assertEquals("丁真笔记本", VendorGuide.APP_LABEL)
        assertEquals("android.settings.ACCESSIBILITY_DETAILS_SETTINGS", VendorGuide.ACTION_ACCESSIBILITY_DETAILS_SETTINGS)
    }
}
