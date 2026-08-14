package com.local.fenbistudy.capture

data class StudyBrowse(
    val query: String = "",
    val paperId: String? = null,
    val folder: String? = null,
    val knowledge: String? = null,
    val onlyWrong: Boolean = true,
)

enum class StudyExport {
    WRONG_ZIP,
    ALL_ZIP,
    HTML,
}

object StudyFilters {
    fun apply(library: StudyLibrary, browse: StudyBrowse): List<StudyQuestion> {
        var items = library.questions
        if (browse.onlyWrong) items = items.filter { it.isCorrect != true }
        browse.paperId?.let { id -> items = items.filter { it.paperId == id } }
        browse.folder?.let { folder -> items = items.filter { it.folderName == folder } }
        browse.knowledge?.let { point -> items = items.filter { point in it.knowledge } }
        val query = browse.query.trim()
        if (query.isNotEmpty()) {
            items = items.filter { question ->
                question.stem.contains(query, ignoreCase = true) ||
                    question.officialAnswer.contains(query, ignoreCase = true) ||
                    question.userAnswer.contains(query, ignoreCase = true) ||
                    question.explanation.contains(query, ignoreCase = true) ||
                    question.folderName.contains(query, ignoreCase = true) ||
                    question.knowledge.any { it.contains(query, ignoreCase = true) }
            }
        }
        return items.sortedWith(compareBy({ it.paperId }, { it.sequence }))
    }

    fun folders(library: StudyLibrary): List<String> =
        library.questions.map { it.folderName.ifBlank { "未分类" } }.distinct().sorted()

    fun knowledge(library: StudyLibrary): List<String> =
        library.questions.flatMap { it.knowledge }.filter { it.isNotBlank() }.distinct().sorted()

    fun paperTitle(library: StudyLibrary, paperId: String?): String =
        library.papers.firstOrNull { it.id == paperId }?.title.orEmpty()
}
