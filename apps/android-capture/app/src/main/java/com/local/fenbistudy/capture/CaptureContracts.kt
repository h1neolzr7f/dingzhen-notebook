package com.local.fenbistudy.capture

/** The three capture modes exposed to the user. */
enum class CaptureMode {
    MANUAL,
    SEMI_AUTO,
    AUTO,
}

enum class CaptureTaskStatus {
    CREATED,
    RUNNING,
    PAUSED,
    FALLBACK_SEMI_AUTO,
    COMPLETED,
    FAILED,
    STOPPED,
}

data class CaptureTask(
    val id: String,
    val title: String,
    val mode: CaptureMode,
    val createdAtEpochMs: Long,
    val outputDirectory: String,
)

/**
 * A small, append-safe checkpoint.  It is persisted after every frame, so a
 * process kill or a broken transfer never discards the raw screenshots.
 */
data class CaptureSessionState(
    val taskId: String,
    val status: CaptureTaskStatus,
    val lastSequence: Long,
    val savedPaths: List<String>,
    val checksums: Map<Long, String>,
    val errorMessage: String? = null,
    /** Separate from capture progress so transfer can resume independently. */
    val lastTransferredSequence: Long = -1,
    val currentQuestion: Int? = null,
    val phase: String = "question",
    val skippedQuestions: List<Int> = emptyList(),
)

interface CaptureTaskStore {
    fun saveTask(task: CaptureTask)
    fun loadTask(taskId: String): CaptureTask?
    fun saveSession(state: CaptureSessionState)
    fun loadSession(taskId: String): CaptureSessionState?
    fun listTasks(): List<CaptureTask>
}

interface TransferClient {
    /** Resume from [state.lastSequence] and return the updated checkpoint. */
    fun transfer(task: CaptureTask, state: CaptureSessionState): CaptureSessionState
}

fun CaptureMode.fallbackOnFailure(): CaptureMode =
    if (this == CaptureMode.AUTO) CaptureMode.SEMI_AUTO else this
