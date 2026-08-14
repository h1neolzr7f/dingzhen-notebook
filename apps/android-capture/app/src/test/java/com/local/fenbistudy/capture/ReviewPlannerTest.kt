package com.local.fenbistudy.capture

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ReviewPlannerTest {
    @Test
    fun stagesMatchDesktopTracks() {
        assertEquals(ReviewStage.MASTERED, ReviewPlanner.stage(q(isCorrect = true, wrongCount = 0, user = "A")))
        assertEquals(ReviewStage.MASTERED, ReviewPlanner.stage(q(isCorrect = true, wrongCount = 2, user = "A")))
        assertEquals(ReviewStage.FIRST, ReviewPlanner.stage(q(isCorrect = false, wrongCount = 1)))
        assertEquals(ReviewStage.SECOND, ReviewPlanner.stage(q(isCorrect = false, wrongCount = 2)))
        assertEquals(ReviewStage.INTERVAL, ReviewPlanner.stage(q(isCorrect = false, wrongCount = 3)))
        assertEquals(ReviewStage.PREVIEW, ReviewPlanner.stage(q(isCorrect = null, user = "")))
    }

    @Test
    fun filtersSearchPaperAndKnowledge() {
        val library = StudyLibrary(
            papers = listOf(StudyPaper("p1", "行测卷一", "test", 1L), StudyPaper("p2", "申论", "test", 2L)),
            questions = listOf(
                q(id = "q1", paperId = "p1", stem = "1+1=?", official = "B", isCorrect = false, knowledge = listOf("算术")),
                q(id = "q2", paperId = "p1", stem = "已掌握加法", official = "A", user = "A", isCorrect = true, knowledge = listOf("算术")),
                q(id = "q3", paperId = "p2", stem = "概括材料", official = "略", isCorrect = false, knowledge = listOf("概括")),
            ),
        )
        val wrong = StudyFilters.apply(library, StudyBrowse(onlyWrong = true))
        assertEquals(listOf("q1", "q3"), wrong.map { it.id })
        val paper = StudyFilters.apply(library, StudyBrowse(paperId = "p1", onlyWrong = false))
        assertEquals(2, paper.size)
        val knowledge = StudyFilters.apply(library, StudyBrowse(knowledge = "概括", onlyWrong = true))
        assertEquals("q3", knowledge.single().id)
        val search = StudyFilters.apply(library, StudyBrowse(query = "加法", onlyWrong = false))
        assertEquals("q2", search.single().id)
        assertTrue(ReviewPlanner.knowledgeTree(library.wrong).containsKey("算术"))
        assertTrue(WrongPaperHtml.render(library).contains("今知错题卷"))
        assertTrue(WrongPaperHtml.render(library).contains("1+1=?"))
        assertTrue(!WrongPaperHtml.render(library).contains("已掌握加法"))
    }

    private fun q(
        id: String = "q",
        paperId: String = "p1",
        stem: String = "题",
        official: String = "B",
        user: String = "A",
        isCorrect: Boolean? = false,
        wrongCount: Int = 1,
        knowledge: List<String> = emptyList(),
    ) = StudyQuestion(
        id = id,
        paperId = paperId,
        sequence = 1,
        stem = stem,
        officialAnswer = official,
        userAnswer = user,
        isCorrect = isCorrect,
        wrongCount = wrongCount,
        knowledge = knowledge,
    )
}
