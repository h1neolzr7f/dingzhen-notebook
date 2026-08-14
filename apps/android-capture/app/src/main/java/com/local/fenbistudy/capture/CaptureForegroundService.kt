package com.local.fenbistudy.capture

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat

class CaptureForegroundService : Service() {
    companion object {
        const val ACTION_START = "com.local.fenbistudy.capture.START"
        const val ACTION_CAPTURE = "com.local.fenbistudy.capture.CAPTURE"
        const val ACTION_PAUSE = "com.local.fenbistudy.capture.PAUSE"
        const val ACTION_RESUME = "com.local.fenbistudy.capture.RESUME"
        const val ACTION_STOP = "com.local.fenbistudy.capture.STOP"
        private const val CHANNEL_ID = "fenbi_capture"
        private const val NOTIFICATION_ID = 701
    }

    private lateinit var store: SharedPreferencesTaskStore
    private lateinit var capture: MediaProjectionCapture
    private lateinit var overlay: FloatingController
    private var currentTaskId: String? = null

    override fun onCreate() {
        super.onCreate()
        store = SharedPreferencesTaskStore(this)
        overlay = FloatingController(this)
        capture = MediaProjectionCapture(this, store) { message -> pauseCapture(message) }
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> startCapture(intent)
            ACTION_CAPTURE -> capture.requestFrame()
            ACTION_PAUSE -> pauseCapture(null)
            ACTION_RESUME -> capture.resume()
            ACTION_STOP -> stopCapture()
        }
        return START_NOT_STICKY
    }

    private fun startCapture(intent: Intent) {
        val taskId = intent.getStringExtra(MediaProjectionCapture.EXTRA_TASK_ID) ?: return stopSelf()
        val task = store.loadTask(taskId) ?: return stopSelf()
        currentTaskId = taskId
        val resultCode = intent.getIntExtra(MediaProjectionCapture.EXTRA_RESULT_CODE, -1)
        val resultData = if (Build.VERSION.SDK_INT >= 33) {
            intent.getParcelableExtra(MediaProjectionCapture.EXTRA_RESULT_DATA, Intent::class.java)
        } else {
            @Suppress("DEPRECATION") intent.getParcelableExtra(MediaProjectionCapture.EXTRA_RESULT_DATA)
        } ?: return stopSelf()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification(task.title), foregroundType())
        } else {
            @Suppress("DEPRECATION") startForeground(NOTIFICATION_ID, notification(task.title))
        }
        if (!capture.start(resultCode, resultData, task)) {
            pauseCapture("屏幕采集启动失败")
            return
        }
        CaptureRuntime.bind(
            task.mode,
            onCapture = capture::requestFrame,
            onPause = ::pauseCapture,
            onResume = capture::resume,
            onStop = ::stopCapture,
            onQuestionChanged = ::updateQuestion,
            onStatus = overlay::updateStatus,
        )
        overlay.show(
            onCapture = capture::requestFrame,
            onPause = { pauseCapture(null) },
            onResume = capture::resume,
            onMarkQuestion = { markPhase("question") },
            onMarkAnalysis = { markPhase("analysis") },
            onRetry = capture::requestFrame,
            onSkip = ::skipQuestion,
            onStop = ::stopCapture,
        )
        if (task.mode == CaptureMode.MANUAL) capture.requestFrame()
    }

    private fun pauseCapture(reason: String?) {
        capture.pause()
        val id = currentTaskId ?: return
        if (!reason.isNullOrBlank()) {
            store.loadSession(id)?.let { store.saveSession(it.copy(status = CaptureTaskStatus.PAUSED, errorMessage = reason)) }
        }
    }

    private fun updateQuestion(number: Int) {
        overlay.updateQuestion(number)
        val id = currentTaskId ?: return
        store.loadSession(id)?.let { store.saveSession(it.copy(currentQuestion = number)) }
    }

    private fun markPhase(phase: String) {
        val id = currentTaskId ?: return
        store.loadSession(id)?.let { store.saveSession(it.copy(phase = phase)) }
        capture.requestFrame()
    }

    private fun skipQuestion() {
        val id = currentTaskId ?: return
        store.loadSession(id)?.let { state ->
            val number = state.currentQuestion
            store.saveSession(state.copy(skippedQuestions = if (number == null) state.skippedQuestions else (state.skippedQuestions + number).distinct()))
        }
        CaptureRuntime.requestNextQuestion()
    }

    private fun stopCapture() {
        capture.stop()
        overlay.hide()
        CaptureRuntime.clear()
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun foregroundType(): Int =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION
        } else 0

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            getSystemService(NotificationManager::class.java).createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "丁真笔记本", NotificationManager.IMPORTANCE_LOW),
            )
        }
    }

    private fun serviceAction(action: String, requestCode: Int): PendingIntent = PendingIntent.getService(
        this,
        requestCode,
        Intent(this, CaptureForegroundService::class.java).setAction(action),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
    )

    private fun notification(title: String): Notification =
        NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_menu_camera)
            .setContentTitle("正在录制整块屏幕")
            .setContentText("在已打开的粉笔试卷里用：$title")
            .setOngoing(true)
            .setContentIntent(PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE))
            .addAction(0, "截图", serviceAction(ACTION_CAPTURE, 1))
            .addAction(0, "暂停", serviceAction(ACTION_PAUSE, 2))
            .addAction(0, "停止", serviceAction(ACTION_STOP, 3))
            .build()

    override fun onDestroy() {
        runCatching { capture.stop() }
        overlay.hide()
        CaptureRuntime.clear()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
