package com.local.fenbistudy.capture

import android.content.Context
import android.content.Intent

/** Only official 粉笔 clients. Never 猿题库 / 小猿搜题 / 小猿口算. */
object FenbiAppGuard {
    val KNOWN_PACKAGES = listOf(
        "com.fenbi.android.servant",
        "com.fenbi.android.zhaokao",
        "com.fenbi.android.kecheng",
        "com.fenbi.android.gaozhong",
        "com.fenbi.gwyk12",
        "com.fenbi",
    )

    val BLOCKED_PACKAGES = setOf(
        "com.fenbi.android.solar",
        "com.fenbi.android.leo",
        "com.yuantiku",
        "com.yuantiku.android",
        "com.yuanfudao.android",
    )

    fun isFenbi(packageName: String?): Boolean {
        val name = packageName?.trim()?.lowercase().orEmpty()
        if (name.isEmpty() || name in BLOCKED_PACKAGES) return false
        return name in KNOWN_PACKAGES
    }

    fun pickLaunchPackage(installed: Collection<String>): String? {
        val present = installed.map { it.trim().lowercase() }.toSet()
        return KNOWN_PACKAGES.firstOrNull { it in present && it !in BLOCKED_PACKAGES }
    }

    /** Bring the already-installed 粉笔 app forward. Never opens 猿题库. */
    fun launchInstalledFenbi(context: Context): Boolean {
        val pm = context.packageManager
        val target = KNOWN_PACKAGES.firstOrNull { pkg ->
            isFenbi(pkg) && pm.getLaunchIntentForPackage(pkg) != null
        } ?: return false
        val launch = pm.getLaunchIntentForPackage(target) ?: return false
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)
        context.startActivity(launch)
        return true
    }

    fun isSystemDialogPackage(packageName: String?): Boolean {
        val name = packageName?.trim()?.lowercase().orEmpty()
        return name in setOf(
            "android",
            "com.android.systemui",
            "com.android.permissioncontroller",
            "com.google.android.permissioncontroller",
        )
    }
}
