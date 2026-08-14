package com.local.fenbistudy.capture

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.os.SystemClock
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

/** Only drives Fenbi completed-paper pages after the user has logged in. */
class AutomationAccessibilityService : AccessibilityService() {
    private var policy = AutomationPolicy()
    private var previousTextHash: Int? = null
    private var lastHandledAt = 0L

    override fun onServiceConnected() {
        CaptureRuntime.bindNextQuestion { clickFirst("下一题", "下一题>") }
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (!CaptureRuntime.active || CaptureRuntime.mode == CaptureMode.MANUAL) return
        val now = SystemClock.elapsedRealtime()
        if (now - lastHandledAt < 1_200) return
        val root = rootInActiveWindow ?: return
        lastHandledAt = now
        val packageName = event?.packageName?.toString() ?: root.packageName?.toString()
        policy.select(CaptureRuntime.mode)
        if (!FenbiAppGuard.isFenbi(packageName)) {
            CaptureRuntime.setStatus("请回到已经打开的粉笔。本软件不会登录粉笔。")
            return
        }
        val text = collectText(root)
        val hash = text.hashCode()
        val snapshot = FenbiPageClassifier.classify(
            packageName,
            text,
            previousTextHash == null || previousTextHash != hash,
        )
        previousTextHash = hash
        snapshot.questionNumber?.let(CaptureRuntime::reportQuestion)
        when (policy.decide(snapshot)) {
            AutomationAction.WAIT_FOR_LOGIN ->
                CaptureRuntime.setStatus("本软件不会登录粉笔。请在粉笔官方 App 里进入已完成试卷。")
            AutomationAction.WAIT_FOR_PAPER ->
                CaptureRuntime.setStatus("请打开一套已完成的试卷（带解析）")
            AutomationAction.WAIT_FOR_FENBI ->
                CaptureRuntime.setStatus("请回到粉笔 App")
            AutomationAction.WAIT_FOR_USER ->
                CaptureRuntime.setStatus("本题已齐，请手动进入下一题")
            AutomationAction.OPEN_ANALYSIS -> {
                CaptureRuntime.requestCapture()
                if (!clickFirst("查看解析", "查看本题解析")) {
                    CaptureRuntime.setStatus("请点「查看解析」")
                }
            }
            AutomationAction.SCROLL -> {
                CaptureRuntime.requestCapture()
                if (!scrollForward(root)) swipeUp()
            }
            AutomationAction.NEXT_QUESTION -> {
                CaptureRuntime.requestCapture()
                if (!clickFirst("下一题", "下一题>")) {
                    CaptureRuntime.setStatus("没有下一题，本卷采集结束")
                    CaptureRuntime.stop()
                }
            }
            AutomationAction.FINISH_PAPER -> {
                CaptureRuntime.requestCapture()
                CaptureRuntime.setStatus("本卷已采完，交给电脑自动识别")
                CaptureRuntime.stop()
            }
            AutomationAction.PAUSE_ERROR ->
                CaptureRuntime.pause("页面异常、网络错误或连续三次未变化，已安全暂停")
            AutomationAction.CAPTURE -> CaptureRuntime.requestCapture()
        }
    }

    private fun collectText(root: AccessibilityNodeInfo): String {
        val values = ArrayList<String>()
        fun visit(node: AccessibilityNodeInfo) {
            node.text?.toString()?.takeIf { it.isNotBlank() }?.let(values::add)
            node.contentDescription?.toString()?.takeIf { it.isNotBlank() }?.let(values::add)
            for (index in 0 until node.childCount) node.getChild(index)?.let(::visit)
        }
        visit(root)
        return values.joinToString("\n")
    }

    private fun scrollForward(root: AccessibilityNodeInfo): Boolean {
        fun find(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
            if (node.isScrollable && node.isEnabled) return node
            for (index in 0 until node.childCount) find(node.getChild(index) ?: continue)?.let { return it }
            return null
        }
        return find(root)?.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD) == true
    }

    private fun clickFirst(vararg anchors: String): Boolean {
        val root = rootInActiveWindow ?: return false
        for (anchor in anchors) {
            val clicked = root.findAccessibilityNodeInfosByText(anchor)
                .asSequence()
                .mapNotNull { node -> generateSequence(node) { it.parent }.firstOrNull { it.isClickable && it.isEnabled } }
                .firstOrNull()
                ?.performAction(AccessibilityNodeInfo.ACTION_CLICK) == true
            if (clicked) return true
        }
        return false
    }

    private fun swipeUp(): Boolean {
        val metrics = resources.displayMetrics
        val path = Path().apply {
            moveTo(metrics.widthPixels * 0.5f, metrics.heightPixels * 0.78f)
            lineTo(metrics.widthPixels * 0.5f, metrics.heightPixels * 0.28f)
        }
        return dispatchGesture(GestureDescription.Builder().addStroke(GestureDescription.StrokeDescription(path, 0, 550)).build(), null, null)
    }

    override fun onInterrupt() {
        CaptureRuntime.pause("自动操作服务被系统中断")
    }

    override fun onDestroy() {
        CaptureRuntime.bindNextQuestion(null)
        super.onDestroy()
    }
}
