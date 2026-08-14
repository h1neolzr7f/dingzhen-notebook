package com.local.fenbistudy.capture

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AutomationPolicyTest {
    @Test
    fun loginWaitsInsteadOfFailingSoUserCanSignIn() {
        val policy = AutomationPolicy(CaptureMode.AUTO)
        assertEquals(AutomationAction.WAIT_FOR_LOGIN, policy.decide(PageSnapshot(kind = PageKind.LOGIN)))
        assertEquals(
            AutomationAction.SCROLL,
            policy.decide(
                PageSnapshot(
                    kind = PageKind.ANALYSIS,
                    questionNumber = 1,
                    hasUserAnswer = true,
                    hasOfficialAnswer = true,
                ),
            ),
        )
    }

    @Test
    fun foreignAppAndHomeWaitWithoutGestures() {
        val policy = AutomationPolicy(CaptureMode.AUTO)
        assertEquals(AutomationAction.WAIT_FOR_FENBI, policy.decide(PageSnapshot(kind = PageKind.FOREIGN_APP)))
        assertEquals(AutomationAction.WAIT_FOR_PAPER, policy.decide(PageSnapshot(kind = PageKind.HOME)))
    }

    @Test
    fun automaticModeNeverContinuesThroughUnsafePages() {
        val policy = AutomationPolicy(CaptureMode.AUTO)
        for (kind in listOf(PageKind.NETWORK_ERROR, PageKind.POPUP)) {
            assertEquals(AutomationAction.PAUSE_ERROR, policy.decide(PageSnapshot(kind = kind)))
        }
    }

    @Test
    fun automaticModeRequiresAnswerAndCompleteExplanationBeforeNextQuestion() {
        val policy = AutomationPolicy(CaptureMode.AUTO)
        assertEquals(
            AutomationAction.SCROLL,
            policy.decide(PageSnapshot(questionNumber = 7, hasUserAnswer = true, hasOfficialAnswer = true)),
        )
        assertEquals(
            AutomationAction.NEXT_QUESTION,
            policy.decide(
                PageSnapshot(
                    questionNumber = 7,
                    hasUserAnswer = true,
                    hasOfficialAnswer = true,
                    hasOfficialExplanation = true,
                    atExplanationEnd = true,
                    hasNextQuestion = true,
                ),
            ),
        )
        assertEquals(
            AutomationAction.FINISH_PAPER,
            policy.decide(
                PageSnapshot(
                    questionNumber = 8,
                    hasUserAnswer = true,
                    hasOfficialAnswer = true,
                    hasOfficialExplanation = true,
                    atExplanationEnd = true,
                    paperEnded = true,
                ),
            ),
        )
    }

    @Test
    fun opensOfficialAnalysisWhenFenbiShowsTheEntry() {
        val policy = AutomationPolicy(CaptureMode.AUTO)
        assertEquals(
            AutomationAction.OPEN_ANALYSIS,
            policy.decide(PageSnapshot(questionNumber = 2, hasUserAnswer = true, needsOpenAnalysis = true)),
        )
    }

    @Test
    fun threeUnchangedPagesPauseInsteadOfBlindlyScrolling() {
        val policy = AutomationPolicy(CaptureMode.AUTO)
        repeat(2) {
            policy.select(CaptureMode.AUTO)
            assertEquals(AutomationAction.SCROLL, policy.decide(PageSnapshot(questionNumber = 3, changed = false)))
        }
        policy.select(CaptureMode.AUTO)
        assertEquals(AutomationAction.PAUSE_ERROR, policy.decide(PageSnapshot(questionNumber = 3, changed = false)))
    }

    @Test
    fun semiAutomaticModeStopsAtACompleteQuestionForUserNavigation() {
        val policy = AutomationPolicy(CaptureMode.SEMI_AUTO)
        assertEquals(
            AutomationAction.WAIT_FOR_USER,
            policy.decide(
                PageSnapshot(
                    questionNumber = 2,
                    hasUserAnswer = true,
                    hasOfficialAnswer = true,
                    hasOfficialExplanation = true,
                    atExplanationEnd = true,
                ),
            ),
        )
    }
}

class FenbiPageClassifierTest {
    @Test
    fun ignoresOtherAppsAndDoesNotTreatCancelAsPopup() {
        val wechat = FenbiPageClassifier.classify("com.tencent.mm", "取消 发送", true)
        assertEquals(PageKind.FOREIGN_APP, wechat.kind)
        assertFalse(FenbiAppGuard.isFenbi("com.tencent.mm"))
        assertTrue(FenbiAppGuard.isFenbi("com.fenbi.android.servant"))

        val analysis = FenbiPageClassifier.classify(
            "com.fenbi.android.servant",
            "第3题\n你的答案 A\n正确答案 B\n答案解析 理由\n取消收藏\n下一题",
            true,
        )
        assertEquals(PageKind.ANALYSIS, analysis.kind)
        assertEquals(3, analysis.questionNumber)
        assertTrue(analysis.hasOfficialExplanation)

        val yuantiku = FenbiPageClassifier.classify(
            "com.fenbi.android.solar",
            "手机号登录\n验证码登录\n密码登录",
            true,
        )
        assertEquals(PageKind.FOREIGN_APP, yuantiku.kind)

        val login = FenbiPageClassifier.classify(
            "com.fenbi.android.servant",
            "手机号登录\n验证码登录\n密码登录",
            true,
        )
        assertEquals(PageKind.LOGIN, login.kind)
    }
}
