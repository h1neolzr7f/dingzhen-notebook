package com.local.fenbistudy.capture

enum class PageKind { QUESTION, ANALYSIS, LOGIN, NETWORK_ERROR, POPUP, HOME, FOREIGN_APP, UNKNOWN }
enum class AutomationAction {
    CAPTURE,
    SCROLL,
    NEXT_QUESTION,
    OPEN_ANALYSIS,
    WAIT_FOR_USER,
    WAIT_FOR_LOGIN,
    WAIT_FOR_PAPER,
    WAIT_FOR_FENBI,
    FINISH_PAPER,
    PAUSE_ERROR,
}

data class PageSnapshot(
    val kind: PageKind = PageKind.QUESTION,
    val questionNumber: Int? = null,
    val hasUserAnswer: Boolean = false,
    val hasOfficialAnswer: Boolean = false,
    val hasOfficialExplanation: Boolean = false,
    val atExplanationEnd: Boolean = false,
    val changed: Boolean = true,
    val needsOpenAnalysis: Boolean = false,
    val paperEnded: Boolean = false,
    val hasNextQuestion: Boolean = false,
)

/** Fail-closed decisions for manual, semi-automatic and automatic capture. */
class AutomationPolicy(initialMode: CaptureMode = CaptureMode.SEMI_AUTO) {
    var mode: CaptureMode = initialMode
        private set
    private var unchanged = 0

    fun select(next: CaptureMode) {
        if (mode != next) {
            mode = next
            unchanged = 0
        }
    }

    fun decide(page: PageSnapshot): AutomationAction {
        if (mode == CaptureMode.MANUAL) return AutomationAction.WAIT_FOR_USER
        if (page.kind == PageKind.FOREIGN_APP) return AutomationAction.WAIT_FOR_FENBI
        if (page.kind == PageKind.LOGIN) return AutomationAction.WAIT_FOR_LOGIN
        if (page.kind == PageKind.HOME) return AutomationAction.WAIT_FOR_PAPER
        if (page.kind in setOf(PageKind.NETWORK_ERROR, PageKind.POPUP)) {
            return AutomationAction.PAUSE_ERROR
        }
        unchanged = if (page.changed) 0 else unchanged + 1
        if (unchanged >= 3) return AutomationAction.PAUSE_ERROR
        if (page.needsOpenAnalysis) return AutomationAction.OPEN_ANALYSIS
        val complete = page.hasUserAnswer && page.hasOfficialAnswer &&
            page.hasOfficialExplanation && page.atExplanationEnd
        if (!complete) return AutomationAction.SCROLL
        if (mode == CaptureMode.AUTO && (page.paperEnded || !page.hasNextQuestion)) {
            return AutomationAction.FINISH_PAPER
        }
        return if (mode == CaptureMode.AUTO) AutomationAction.NEXT_QUESTION else AutomationAction.WAIT_FOR_USER
    }
}
