package com.local.fenbistudy.capture

import android.content.ClipData
import android.content.ClipboardManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.provider.Settings

enum class VendorFamily {
    XIAOMI,
    HUAWEI,
    OPPO,
    VIVO,
    OTHER,
}

object VendorGuide {
    const val SERVICE_LABEL = "丁真自动翻页"
    const val APP_LABEL = "丁真笔记本"
    const val ACTION_ACCESSIBILITY_DETAILS_SETTINGS = "android.settings.ACCESSIBILITY_DETAILS_SETTINGS"

    fun family(manufacturer: String, brand: String, extra: String = ""): VendorFamily {
        val blob = "$manufacturer $brand $extra".lowercase()
        return when {
            listOf("xiaomi", "redmi", "poco", "blackshark", "miui", "hyperos").any { it in blob } -> VendorFamily.XIAOMI
            listOf("huawei", "honor").any { it in blob } -> VendorFamily.HUAWEI
            listOf("oppo", "realme", "oneplus").any { it in blob } -> VendorFamily.OPPO
            listOf("vivo", "iqoo").any { it in blob } -> VendorFamily.VIVO
            else -> VendorFamily.OTHER
        }
    }

    fun currentFamily(): VendorFamily = family(
        android.os.Build.MANUFACTURER.orEmpty(),
        android.os.Build.BRAND.orEmpty(),
        listOf(android.os.Build.DISPLAY, android.os.Build.PRODUCT, android.os.Build.MODEL).joinToString(" "),
    )

    fun title(family: VendorFamily): String = when (family) {
        VendorFamily.XIAOMI -> "点一下进入开关页。进去后只打开「$SERVICE_LABEL」，再按返回。"
        else -> "点一下进入开关页，打开「$SERVICE_LABEL」后按返回，会自动开始。"
    }

    fun steps(family: VendorFamily): List<String> = buildList {
        add("点下面大按钮，会尽量直接进到「$SERVICE_LABEL」开关。")
        add("打开那个开关，系统弹窗点允许。")
        add("按返回。如果是从「开始采集」进来的，会自动继续。")
        if (family == VendorFamily.XIAOMI) {
            add("小米若只看到系统项，滑到最底下点「已下载的服务」。")
        }
    }

    fun searchHint(): String = "如果进的是列表：滑到最底下点「已下载的服务」，再打开「$SERVICE_LABEL」。"

    fun serviceComponent(context: Context): ComponentName =
        ComponentName(context, AutomationAccessibilityService::class.java)

    fun copyServiceName(context: Context) {
        val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        clipboard.setPrimaryClip(ClipData.newPlainText("accessibility", SERVICE_LABEL))
    }

    fun openAccessibilityToggle(context: Context): Boolean =
        launchFirst(context, accessibilityIntents(serviceComponent(context)))

    fun openAccessibilityList(context: Context): Boolean =
        launchFirst(context, listOf(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)))

    fun openXiaomiAutostart(context: Context): Boolean = launchFirst(
        context,
        listOf(
            Intent().setClassName("com.miui.securitycenter", "com.miui.permcenter.autostart.AutoStartManagementActivity"),
            Intent("miui.intent.action.OP_AUTO_START").addCategory(Intent.CATEGORY_DEFAULT),
        ),
    )

    fun firstLaunchable(context: Context, intents: List<Intent>): Intent? {
        for (raw in intents) {
            try {
                val intent = Intent(raw)
                if (intent.resolveActivity(context.packageManager) != null) return intent
            } catch (_: Exception) {
                continue
            }
        }
        return intents.firstOrNull()
    }

    fun accessibilityIntents(component: ComponentName): List<Intent> {
        val key = component.flattenToString()
        val args = Bundle().apply {
            putParcelable(Intent.EXTRA_COMPONENT_NAME, component)
            putString(":settings:fragment_args_key", key)
            putString("component_name", key)
        }
        return buildList {
            if (Build.VERSION.SDK_INT >= 30) {
                add(detailsIntent(component).setPackage("com.android.settings"))
                add(detailsIntent(component))
                add(
                    Intent(ACTION_ACCESSIBILITY_DETAILS_SETTINGS)
                        .putExtra(Intent.EXTRA_COMPONENT_NAME, key)
                        .setPackage("com.android.settings"),
                )
            }
            add(subSettings("com.android.settings.accessibility.ToggleAccessibilityServicePreferenceFragment", args))
            add(subSettings("com.android.settings.accessibility.AccessibilityDetailsSettingsFragment", args))
            add(
                Intent().setClassName(
                    "com.android.settings",
                    "com.android.settings.Settings\$AccessibilityDetailsSettingsActivity",
                ).putExtra(Intent.EXTRA_COMPONENT_NAME, component),
            )
            add(
                Intent().setClassName(
                    "com.android.settings",
                    "com.android.settings.Settings\$AccessibilityInstalledFromOtherAppsActivity",
                ),
            )
            add(highlightInList(component))
            add(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }
    }

    private fun detailsIntent(component: ComponentName): Intent =
        Intent(ACTION_ACCESSIBILITY_DETAILS_SETTINGS).putExtra(Intent.EXTRA_COMPONENT_NAME, component)

    private fun subSettings(fragment: String, args: Bundle): Intent =
        Intent(Intent.ACTION_MAIN)
            .setClassName("com.android.settings", "com.android.settings.SubSettings")
            .putExtra(":settings:show_fragment", fragment)
            .putExtra(":settings:show_fragment_args", args)
            .putExtra(":settings:show_fragment_title", SERVICE_LABEL)

    private fun highlightInList(component: ComponentName): Intent {
        val key = component.flattenToString()
        return Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).apply {
            putExtra(":settings:fragment_args_key", key)
            putExtra(
                ":settings:show_fragment_args",
                Bundle().apply { putString(":settings:fragment_args_key", key) },
            )
        }
    }

    fun launchFirst(context: Context, intents: List<Intent>): Boolean {
        for (raw in intents) {
            val intent = Intent(raw).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            try {
                context.startActivity(intent)
                return true
            } catch (_: Exception) {
                continue
            }
        }
        return false
    }
}
