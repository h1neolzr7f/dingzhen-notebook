package com.local.fenbistudy.capture

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/** SharedPreferences-backed task/checkpoint store; no account tokens are stored. */
class SharedPreferencesTaskStore(context: Context) : CaptureTaskStore {
    private val preferences = context.getSharedPreferences("capture_tasks", Context.MODE_PRIVATE)

    override fun saveTask(task: CaptureTask) {
        val json = JSONObject()
            .put("id", task.id)
            .put("title", task.title)
            .put("mode", task.mode.name)
            .put("createdAtEpochMs", task.createdAtEpochMs)
            .put("outputDirectory", task.outputDirectory)
        preferences.edit().putString("task:${task.id}", json.toString()).apply()
    }

    override fun loadTask(taskId: String): CaptureTask? {
        val raw = preferences.getString("task:$taskId", null) ?: return null
        return runCatching {
            val json = JSONObject(raw)
            CaptureTask(
                id = json.getString("id"),
                title = json.getString("title"),
                mode = CaptureMode.valueOf(json.getString("mode")),
                createdAtEpochMs = json.getLong("createdAtEpochMs"),
                outputDirectory = json.getString("outputDirectory"),
            )
        }.getOrNull()
    }

    override fun listTasks(): List<CaptureTask> = preferences.all.keys
        .asSequence()
        .filter { it.startsWith("task:") }
        .mapNotNull { loadTask(it.removePrefix("task:")) }
        .sortedByDescending { it.createdAtEpochMs }
        .toList()

    override fun saveSession(state: CaptureSessionState) {
        val paths = JSONArray()
        state.savedPaths.forEach(paths::put)
        val checksums = JSONObject()
        state.checksums.forEach { (sequence, checksum) -> checksums.put(sequence.toString(), checksum) }
        val skipped = JSONArray()
        state.skippedQuestions.forEach(skipped::put)
        val json = JSONObject()
            .put("taskId", state.taskId)
            .put("status", state.status.name)
            .put("lastSequence", state.lastSequence)
            .put("lastTransferredSequence", state.lastTransferredSequence)
            .put("savedPaths", paths)
            .put("checksums", checksums)
            .put("phase", state.phase)
            .put("skippedQuestions", skipped)
        state.currentQuestion?.let { json.put("currentQuestion", it) }
        state.errorMessage?.let { json.put("errorMessage", it.take(500)) }
        preferences.edit().putString("session:${state.taskId}", json.toString()).apply()
    }

    override fun loadSession(taskId: String): CaptureSessionState? {
        val raw = preferences.getString("session:$taskId", null) ?: return null
        return runCatching {
            val json = JSONObject(raw)
            val pathsJson = json.optJSONArray("savedPaths") ?: JSONArray()
            val paths = buildList {
                for (index in 0 until pathsJson.length()) add(pathsJson.getString(index))
            }
            val checksumJson = json.optJSONObject("checksums") ?: JSONObject()
            val checksums = buildMap {
                val keys = checksumJson.keys()
                while (keys.hasNext()) {
                    val key = keys.next()
                    put(key.toLong(), checksumJson.getString(key))
                }
            }
            val skippedJson = json.optJSONArray("skippedQuestions") ?: JSONArray()
            val skipped = buildList {
                for (index in 0 until skippedJson.length()) add(skippedJson.getInt(index))
            }
            CaptureSessionState(
                taskId = json.getString("taskId"),
                status = CaptureTaskStatus.valueOf(json.getString("status")),
                lastSequence = json.getLong("lastSequence"),
                lastTransferredSequence = json.optLong("lastTransferredSequence", -1),
                savedPaths = paths,
                checksums = checksums,
                errorMessage = json.optString("errorMessage").takeIf { it.isNotBlank() },
                currentQuestion = if (json.has("currentQuestion")) json.getInt("currentQuestion") else null,
                phase = json.optString("phase", "question"),
                skippedQuestions = skipped,
            )
        }.getOrNull()
    }
}
