package com.local.fenbistudy.capture

/** Same local tracks as desktop/今知：预习 / 一刷 / 二刷 / 间隔 / 已掌握. */
object ReviewPlanner {
    fun stage(question: StudyQuestion): ReviewStage {
        if (question.isCorrect == true) return ReviewStage.MASTERED
        if (question.isCorrect == false) {
            val wrongs = maxOf(1, question.wrongCount)
            return when {
                wrongs >= 3 -> ReviewStage.INTERVAL
                wrongs == 2 -> ReviewStage.SECOND
                else -> ReviewStage.FIRST
            }
        }
        if (question.userAnswer.isBlank()) return ReviewStage.PREVIEW
        return ReviewStage.FIRST
    }

    fun group(questions: List<StudyQuestion>): Map<ReviewStage, List<StudyQuestion>> =
        ReviewStage.entries.associateWith { stage -> questions.filter { stage(it) == stage } }

    fun knowledgeTree(questions: List<StudyQuestion>): Map<String, List<StudyQuestion>> {
        val tree = linkedMapOf<String, MutableList<StudyQuestion>>()
        questions.forEach { question ->
            val points = question.knowledge.ifEmpty { listOf("未标注知识点") }
            points.forEach { point -> tree.getOrPut(point.ifBlank { "未标注知识点" }) { mutableListOf() }.add(question) }
        }
        return tree
    }
}
