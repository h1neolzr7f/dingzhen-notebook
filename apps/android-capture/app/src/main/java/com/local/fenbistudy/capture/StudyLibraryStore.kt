package com.local.fenbistudy.capture

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

class StudyLibraryStore(context: Context) {
    private val file = File(context.filesDir, "study/library.json")

    fun load(): StudyLibrary {
        if (!file.exists()) return StudyLibrary()
        return runCatching { parse(JSONObject(file.readText())) }.getOrDefault(StudyLibrary())
    }

    fun save(library: StudyLibrary) {
        file.parentFile?.mkdirs()
        file.writeText(toJson(library).toString())
    }

    fun upsertPaper(paper: StudyPaper, questions: List<StudyQuestion> = emptyList()): StudyLibrary {
        val current = load()
        val papers = current.papers.filterNot { it.id == paper.id } + paper
        val nextQuestions = if (questions.isEmpty()) {
            current.questions
        } else {
            current.questions.filterNot { it.paperId == paper.id } + questions
        }
        val next = StudyLibrary(papers.sortedByDescending { it.createdAtEpochMs }, nextQuestions)
        save(next)
        return next
    }

    fun replaceQuestion(question: StudyQuestion): StudyLibrary {
        val current = load()
        val next = current.copy(questions = current.questions.map { if (it.id == question.id) question else it })
        save(next)
        return next
    }

    fun deleteQuestion(questionId: String): StudyLibrary {
        val current = load()
        val next = current.copy(questions = current.questions.filterNot { it.id == questionId })
        save(next)
        return next
    }

    fun deletePaper(paperId: String): StudyLibrary {
        val current = load()
        val next = StudyLibrary(
            papers = current.papers.filterNot { it.id == paperId },
            questions = current.questions.filterNot { it.paperId == paperId },
        )
        save(next)
        return next
    }

    fun merge(other: StudyLibrary): StudyLibrary {
        val current = load()
        val papers = (current.papers + other.papers).distinctBy { it.id }
        val questions = (current.questions + other.questions).distinctBy { it.id }
        val next = StudyLibrary(papers.sortedByDescending { it.createdAtEpochMs }, questions)
        save(next)
        return next
    }

    companion object {
        fun toJson(library: StudyLibrary): JSONObject {
            val papers = JSONArray()
            library.papers.forEach { paper ->
                papers.put(
                    JSONObject()
                        .put("id", paper.id)
                        .put("title", paper.title)
                        .put("source", paper.source)
                        .put("createdAtEpochMs", paper.createdAtEpochMs)
                        .put("pendingFrames", paper.pendingFrames),
                )
            }
            val questions = JSONArray()
            library.questions.forEach { question ->
                questions.put(
                    JSONObject()
                        .put("id", question.id)
                        .put("paperId", question.paperId)
                        .put("sequence", question.sequence)
                        .put("folderName", question.folderName)
                        .put("stem", question.stem)
                        .put("officialAnswer", question.officialAnswer)
                        .put("userAnswer", question.userAnswer)
                        .put("explanation", question.explanation)
                        .put("knowledge", JSONArray(question.knowledge))
                        .put("isCorrect", question.isCorrect ?: JSONObject.NULL)
                        .put("wrongCount", question.wrongCount)
                        .put("tags", JSONArray(question.tags)),
                )
            }
            return JSONObject().put("papers", papers).put("questions", questions)
        }

        fun parse(json: JSONObject): StudyLibrary {
            val papersJson = json.optJSONArray("papers") ?: JSONArray()
            val questionsJson = json.optJSONArray("questions") ?: JSONArray()
            val papers = buildList {
                for (index in 0 until papersJson.length()) {
                    val item = papersJson.getJSONObject(index)
                    add(
                        StudyPaper(
                            id = item.getString("id"),
                            title = item.optString("title"),
                            source = item.optString("source"),
                            createdAtEpochMs = item.optLong("createdAtEpochMs"),
                            pendingFrames = item.optInt("pendingFrames"),
                        ),
                    )
                }
            }
            val questions = buildList {
                for (index in 0 until questionsJson.length()) {
                    val item = questionsJson.getJSONObject(index)
                    add(
                        StudyQuestion(
                            id = item.getString("id"),
                            paperId = item.optString("paperId"),
                            sequence = item.optInt("sequence"),
                            folderName = item.optString("folderName", "未分类"),
                            stem = item.optString("stem"),
                            officialAnswer = item.optString("officialAnswer"),
                            userAnswer = item.optString("userAnswer"),
                            explanation = item.optString("explanation"),
                            knowledge = stringList(item.optJSONArray("knowledge")),
                            isCorrect = if (item.isNull("isCorrect")) null else item.optBoolean("isCorrect"),
                            wrongCount = item.optInt("wrongCount"),
                            tags = stringList(item.optJSONArray("tags")),
                        ),
                    )
                }
            }
            return StudyLibrary(papers, questions)
        }

        private fun stringList(array: JSONArray?): List<String> {
            if (array == null) return emptyList()
            return buildList {
                for (index in 0 until array.length()) add(array.optString(index))
            }
        }
    }
}
