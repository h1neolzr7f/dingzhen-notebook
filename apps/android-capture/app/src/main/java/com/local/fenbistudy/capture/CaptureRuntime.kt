package com.local.fenbistudy.capture

/** Process-local bridge; it exposes controls only while the foreground service is alive. */
object CaptureRuntime {
    @Volatile var mode: CaptureMode = CaptureMode.MANUAL
        private set
    @Volatile var active: Boolean = false
        private set
    @Volatile var status: String = "未开始"
        private set

    private var capture: (() -> Unit)? = null
    private var statusChanged: ((String) -> Unit)? = null
    private var pause: ((String?) -> Unit)? = null
    private var resume: (() -> Unit)? = null
    private var stop: (() -> Unit)? = null
    private var questionChanged: ((Int) -> Unit)? = null
    private var nextQuestion: (() -> Unit)? = null

    @Synchronized
    fun bind(
        nextMode: CaptureMode,
        onCapture: () -> Unit,
        onPause: (String?) -> Unit,
        onResume: () -> Unit,
        onStop: () -> Unit,
        onQuestionChanged: (Int) -> Unit,
        onStatus: ((String) -> Unit)? = null,
    ) {
        mode = nextMode
        capture = onCapture
        pause = onPause
        resume = onResume
        stop = onStop
        questionChanged = onQuestionChanged
        statusChanged = onStatus
        active = true
        setStatus("已开始。请在已经登录的粉笔里打开已完成试卷")
    }

    @Synchronized fun bindNextQuestion(callback: (() -> Unit)?) { nextQuestion = callback }
    fun requestCapture() = capture?.invoke()
    fun pause(reason: String? = null) = pause?.invoke(reason)
    fun resume() = resume?.invoke()
    fun stop() = stop?.invoke()
    fun reportQuestion(number: Int) = questionChanged?.invoke(number)
    fun requestNextQuestion() = nextQuestion?.invoke()

    fun setStatus(message: String) {
        status = message
        statusChanged?.invoke(message)
    }

    @Synchronized
    fun clear() {
        active = false
        capture = null
        pause = null
        resume = null
        stop = null
        questionChanged = null
        nextQuestion = null
        statusChanged = null
        mode = CaptureMode.MANUAL
        status = "未开始"
    }
}
