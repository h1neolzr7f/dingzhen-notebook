package com.local.fenbistudy.capture

data class StudyQuestion(
    val id: String,
    val paperId: String,
    val sequence: Int,
    val folderName: String = "未分类",
    val stem: String,
    val officialAnswer: String = "",
    val userAnswer: String = "",
    val explanation: String = "",
    val knowledge: List<String> = emptyList(),
    val isCorrect: Boolean? = null,
    val wrongCount: Int = 0,
    val tags: List<String> = emptyList(),
)

data class StudyPaper(
    val id: String,
    val title: String,
    val source: String,
    val createdAtEpochMs: Long,
    val pendingFrames: Int = 0,
)

data class StudyLibrary(
    val papers: List<StudyPaper> = emptyList(),
    val questions: List<StudyQuestion> = emptyList(),
) {
    val wrong get() = questions.filter { it.isCorrect == false }
    val mastered get() = questions.filter { ReviewPlanner.stage(it) == ReviewStage.MASTERED }
    val dueToday get() = questions.filter { ReviewPlanner.stage(it) != ReviewStage.MASTERED }
}

enum class ReviewStage(val title: String) {
    PREVIEW("预习"),
    FIRST("一刷"),
    SECOND("二刷"),
    INTERVAL("间隔复习"),
    MASTERED("已掌握"),
}

enum class AppTab(val label: String) {
    HOME("首页"),
    CAPTURE("收题"),
    MISTAKES("错题"),
    REVIEW("复习"),
    MINE("我的"),
}
