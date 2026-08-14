package com.local.fenbistudy.capture

/** Deterministic Fenbi page labels. Never invent official answers. */
object FenbiPageClassifier {
    private val QUESTION_NUMBER = Regex("(?:第\\s*)?(\\d{1,3})(?:\\s*题|[./、])")

    fun classify(packageName: String?, text: String, changed: Boolean): PageSnapshot {
        if (!FenbiAppGuard.isFenbi(packageName)) {
            return PageSnapshot(kind = PageKind.FOREIGN_APP, changed = changed)
        }
        val kind = kindOf(packageName, text)
        val hasUser = listOf("你的答案", "我的答案", "用户答案").any(text::contains)
        val hasOfficial = listOf("正确答案", "参考答案", "官方答案").any(text::contains)
        val hasExplanation = listOf("答案解析", "官方解析").any(text::contains)
        val atEnd = listOf("知识点", "题目来源", "本题用时", "下一题").any(text::contains)
        val hasNext = text.contains("下一题")
        val ended = listOf("已是最后一题", "没有下一题", "本卷已结束", "查看报告", "练习报告", "交卷成功", "返回报告").any(text::contains)
        return PageSnapshot(
            kind = kind,
            questionNumber = QUESTION_NUMBER.find(text)?.groupValues?.get(1)?.toIntOrNull(),
            hasUserAnswer = hasUser,
            hasOfficialAnswer = hasOfficial,
            hasOfficialExplanation = hasExplanation,
            atExplanationEnd = atEnd,
            changed = changed,
            needsOpenAnalysis = text.contains("查看解析") && !hasExplanation && (hasUser || kind == PageKind.QUESTION),
            paperEnded = ended,
            hasNextQuestion = hasNext,
        )
    }

    private fun kindOf(packageName: String?, text: String): PageKind {
        if (FenbiAppGuard.isSystemDialogPackage(packageName) || isSystemPermissionDialog(text)) {
            return PageKind.POPUP
        }
        if (isLogin(text)) return PageKind.LOGIN
        if (listOf("网络错误", "加载失败", "重新加载", "连接失败").any(text::contains)) {
            return PageKind.NETWORK_ERROR
        }
        if (listOf("正确答案", "参考答案", "答案解析", "官方解析", "你的答案").any(text::contains)) {
            return if (listOf("答案解析", "官方解析", "正确答案", "参考答案").any(text::contains)) {
                PageKind.ANALYSIS
            } else {
                PageKind.QUESTION
            }
        }
        if (isHome(text)) return PageKind.HOME
        if (text.isBlank()) return PageKind.UNKNOWN
        return PageKind.QUESTION
    }

    private fun isLogin(text: String): Boolean {
        val strong = listOf("手机号登录", "验证码登录", "密码登录", "登录粉笔", "微信登录")
        return strong.any(text::contains) ||
            (text.contains("登录") && text.contains("验证码") && text.contains("密码"))
    }

    private fun isSystemPermissionDialog(text: String): Boolean {
        val grant = text.contains("允许") && (text.contains("拒绝") || text.contains("禁止"))
        val permission = listOf("权限", "录制", "悬浮窗", "无障碍", "辅助功能").any(text::contains)
        return grant && permission
    }

    private fun isHome(text: String): Boolean {
        val homeMarks = listOf("题库", "课程", "发现", "申论", "行测", "我的课程")
        val paperMarks = listOf("你的答案", "正确答案", "答案解析", "查看解析", "下一题")
        return homeMarks.any(text::contains) && paperMarks.none(text::contains)
    }
}
