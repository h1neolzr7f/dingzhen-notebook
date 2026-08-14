package com.local.fenbistudy.capture

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.zip.ZipFile
import java.util.zip.ZipOutputStream
import java.util.zip.ZipEntry

object JinzhiPackageIo {
    fun importText(raw: String): StudyLibrary {
        val json = JSONObject(raw.trim().removePrefix("\uFEFF"))
        return when {
            json.optString("format") == "jinzhi-mistake-package" -> fromJinzhi(json)
            json.has("questions") && json.has("paper") -> fromPaperExport(json)
            json.has("questions") -> fromPaperExport(json)
            else -> throw IllegalArgumentException("不是今知错题包，也不是本工具导出的试卷 JSON")
        }
    }

    fun importZip(file: File): StudyLibrary {
        ZipFile(file).use { zip ->
            val entry = zip.getEntry("manifest.json") ?: zip.entries().toList().firstOrNull { it.name.endsWith(".json") && !it.isDirectory }
                ?: throw IllegalArgumentException("压缩包里没有 manifest.json")
            return importText(zip.getInputStream(entry).bufferedReader().readText())
        }
    }

    fun exportZip(library: StudyLibrary, destination: File, onlyWrong: Boolean = true): File {
        val document = toJinzhi(library, onlyWrong)
        destination.parentFile?.mkdirs()
        ZipOutputStream(destination.outputStream()).use { zip ->
            zip.putNextEntry(ZipEntry("manifest.json"))
            zip.write(document.toString(2).toByteArray(Charsets.UTF_8))
            zip.closeEntry()
        }
        return destination
    }

    fun fromJinzhi(document: JSONObject): StudyLibrary {
        val title = document.optString("title").ifBlank { "导入错题包" }
        val paperId = document.optJSONObject("meta")?.optString("paper_id").orEmpty().ifBlank { "pkg_${System.currentTimeMillis()}" }
        val folders = mutableMapOf<String, String>()
        val foldersJson = document.optJSONArray("folders") ?: JSONArray()
        for (index in 0 until foldersJson.length()) {
            val folder = foldersJson.optJSONObject(index) ?: continue
            folders[folder.optString("id")] = folder.optString("name").ifBlank { "导入错题" }
        }
        val mistakes = document.optJSONArray("mistakes") ?: JSONArray()
        val questions = buildList {
            for (index in 0 until mistakes.length()) {
                val item = mistakes.optJSONObject(index) ?: continue
                val question = item.optJSONObject("question") ?: JSONObject()
                val official = item.optJSONObject("standard_answer") ?: JSONObject()
                val user = item.optJSONObject("user_solution") ?: JSONObject()
                val interaction = item.optJSONObject("interaction")
                val officialText = interaction?.optString("answer").orEmpty().ifBlank { official.optString("text") }
                val userText = user.optString("text")
                val explanation = interaction?.optString("analysis").orEmpty().ifBlank { official.optString("text") }
                val knowledge = stringList(item.optJSONArray("knowledge_points"))
                add(
                    StudyQuestion(
                        id = item.optString("id").ifBlank { "${paperId}_$index" },
                        paperId = paperId,
                        sequence = index + 1,
                        folderName = folders[item.optString("folder_id")] ?: title,
                        stem = question.optString("text"),
                        officialAnswer = officialText,
                        userAnswer = userText,
                        explanation = explanation,
                        knowledge = knowledge,
                        isCorrect = correctness(userText, officialText),
                        tags = stringList(item.optJSONArray("tags")),
                    ),
                )
            }
        }
        val paper = StudyPaper(paperId, title, "jinzhi-import", System.currentTimeMillis())
        return StudyLibrary(listOf(paper), questions)
    }

    fun fromPaperExport(document: JSONObject): StudyLibrary {
        val paperJson = document.optJSONObject("paper") ?: JSONObject()
        val paperId = paperJson.optString("id").ifBlank { "paper_${System.currentTimeMillis()}" }
        val title = paperJson.optString("title").ifBlank { document.optString("title").ifBlank { "导入试卷" } }
        val questionsJson = document.optJSONArray("questions") ?: JSONArray()
        val questions = buildList {
            for (index in 0 until questionsJson.length()) {
                val item = questionsJson.optJSONObject(index) ?: continue
                val official = joinAnswers(item.opt("official_answer"))
                val user = joinAnswers(item.opt("user_answer"))
                add(
                    StudyQuestion(
                        id = item.optString("id").ifBlank { "${paperId}_$index" },
                        paperId = paperId,
                        sequence = item.optInt("sequence", index + 1),
                        folderName = item.optString("section").ifBlank { title },
                        stem = item.optString("stem_md").ifBlank { item.optString("stem") },
                        officialAnswer = official,
                        userAnswer = user,
                        explanation = item.optString("official_explanation_md"),
                        knowledge = stringList(item.optJSONArray("official_knowledge_points")),
                        isCorrect = if (item.has("is_correct") && !item.isNull("is_correct")) item.optBoolean("is_correct") else correctness(user, official),
                    ),
                )
            }
        }
        return StudyLibrary(listOf(StudyPaper(paperId, title, "paper-json", System.currentTimeMillis())), questions)
    }

    fun toJinzhi(library: StudyLibrary, onlyWrong: Boolean): JSONObject {
        val selected = if (onlyWrong) library.questions.filter { it.isCorrect != true } else library.questions
        val folders = JSONArray().put(JSONObject().put("id", "default").put("name", "错题本").put("parent_id", JSONObject.NULL))
        val mistakes = JSONArray()
        selected.forEach { question ->
            mistakes.put(
                JSONObject()
                    .put("id", question.id)
                    .put("kind", "legacy")
                    .put("folder_id", "default")
                    .put("question", JSONObject().put("text", question.stem).put("images", JSONArray()).put("audio", JSONArray()))
                    .put("standard_answer", JSONObject().put("text", question.officialAnswer.ifBlank { question.explanation }).put("images", JSONArray()).put("audio", JSONArray()))
                    .put("user_solution", JSONObject().put("text", question.userAnswer).put("images", JSONArray()).put("audio", JSONArray()))
                    .put("knowledge_points", JSONArray(question.knowledge))
                    .put("tags", JSONArray(question.tags.ifEmpty { listOf("本地错题本") })),
            )
        }
        return JSONObject()
            .put("format", "jinzhi-mistake-package")
            .put("schema_version", 1)
            .put("title", "今知采集错题包")
            .put("folders", folders)
            .put("mistakes", mistakes)
            .put("media", JSONArray())
    }

    private fun joinAnswers(value: Any?): String = when (value) {
        is JSONArray -> buildList { for (index in 0 until value.length()) add(value.optString(index)) }.joinToString("")
        null, JSONObject.NULL -> ""
        else -> value.toString()
    }

    private fun correctness(user: String, official: String): Boolean? {
        if (user.isBlank() || official.isBlank()) return null
        return user.replace(" ", "").uppercase() == official.replace(" ", "").uppercase()
    }

    private fun stringList(array: JSONArray?): List<String> {
        if (array == null) return emptyList()
        return buildList {
            for (index in 0 until array.length()) {
                val value = array.optString(index)
                if (value.isNotBlank()) add(value)
            }
        }
    }
}
