package com.local.fenbistudy.capture

import android.content.ComponentName
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import java.io.File
import java.net.URL
import java.util.UUID
import kotlin.concurrent.thread

class MainActivity : ComponentActivity() {
    private lateinit var store: SharedPreferencesTaskStore
    private lateinit var studyStore: StudyLibraryStore
    private var selectedMode by mutableStateOf(CaptureMode.AUTO)
    private var activeTask: CaptureTask? = null
    private var lanEndpoint by mutableStateOf("")
    private var lanSecret by mutableStateOf("")
    private var transferStatus by mutableStateOf("还没有传输")
    private var taskStatus by mutableStateOf("在已经登录的粉笔里打开已完成试卷")
    private var overlayReady by mutableStateOf(false)
    private var accessibilityReady by mutableStateOf(false)
    private var frameCount by mutableStateOf(0)
    private var capturing by mutableStateOf(false)
    private var library by mutableStateOf(StudyLibrary())
    private var tab by mutableStateOf(AppTab.HOME)
    private var selectedQuestion by mutableStateOf<StudyQuestion?>(null)
    private var reviewStage by mutableStateOf(ReviewStage.FIRST)
    private var mineMessage by mutableStateOf("")
    private var pendingStart = false

    private val projectionLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val task = activeTask ?: return@registerForActivityResult
        val data = result.data
        if (result.resultCode != RESULT_OK || data == null) {
            Toast.makeText(this, "没有打开屏幕录制，截图不会被覆盖", Toast.LENGTH_LONG).show()
            return@registerForActivityResult
        }
        val service = Intent(this, CaptureForegroundService::class.java).apply {
            action = CaptureForegroundService.ACTION_START
            putExtra(MediaProjectionCapture.EXTRA_RESULT_CODE, result.resultCode)
            putExtra(MediaProjectionCapture.EXTRA_RESULT_DATA, data)
            putExtra(MediaProjectionCapture.EXTRA_TASK_ID, task.id)
        }
        ContextCompat.startForegroundService(this, service)
        capturing = true
        tab = AppTab.CAPTURE
        if (FenbiAppGuard.launchInstalledFenbi(this)) {
            taskStatus = "已回到粉笔，请留在已完成试卷里"
        } else {
            taskStatus = "请自己打开已经登录的粉笔试卷"
            Toast.makeText(this, "没找到粉笔官方 App。本软件不会登录粉笔。", Toast.LENGTH_LONG).show()
        }
    }

    private val accessibilityLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        PermissionCoachOverlay.hide(this)
        refreshChecks()
        continuePendingStart()
    }

    private val importLauncher = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) return@registerForActivityResult
        thread(name = "fenbi-import") {
            runCatching {
                val tmp = File(cacheDir, "import-${System.currentTimeMillis()}")
                contentResolver.openInputStream(uri)?.use { input -> tmp.outputStream().use { input.copyTo(it) } }
                    ?: error("读不到文件")
                val imported = if (isZip(tmp)) JinzhiPackageIo.importZip(tmp) else JinzhiPackageIo.importText(tmp.readText(Charsets.UTF_8))
                studyStore.merge(imported)
            }.onSuccess { merged ->
                runOnUiThread {
                    library = merged
                    mineMessage = "已导入，当前共 ${merged.questions.size} 题"
                    tab = AppTab.MISTAKES
                }
            }.onFailure { error ->
                runOnUiThread { mineMessage = "导入失败：${error.message}"; tab = AppTab.MINE }
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = SharedPreferencesTaskStore(this)
        studyStore = StudyLibraryStore(this)
        activeTask = store.listTasks().firstOrNull()
        refreshChecks()
        setContent {
            JinzhiCaptureTheme {
                JinzhiStudyApp(
                    library = library,
                    tab = tab,
                    onTab = { tab = it },
                    selectedQuestion = selectedQuestion,
                    onOpenQuestion = { selectedQuestion = it },
                    onCloseQuestion = { selectedQuestion = null },
                    onMarkQuestion = ::markQuestion,
                    onSaveQuestion = ::saveQuestion,
                    onDeleteQuestion = ::deleteQuestion,
                    reviewStage = reviewStage,
                    onReviewStage = { reviewStage = it },
                    capture = {
                        CaptureHome(
                            selectedMode = selectedMode,
                            taskStatus = taskStatus,
                            frameCount = frameCount,
                            capturing = capturing,
                            overlayReady = overlayReady,
                            accessibilityReady = accessibilityReady,
                            vendorFamily = VendorGuide.currentFamily(),
                            lanEndpoint = lanEndpoint,
                            lanSecret = lanSecret,
                            transferStatus = transferStatus,
                            onModeSelected = { selectedMode = it },
                            onStart = ::createTaskAndRequestProjection,
                            onOpenFenbi = ::openAlreadyLoggedInFenbi,
                            onOverlayPermission = ::openOverlayPermission,
                            onOpenAccessibilityToggle = ::openAccessibilityToggle,
                            onOpenAccessibilityList = ::openAccessibilityList,
                            onCopyServiceName = ::copyAccessibilityName,
                            onUseManualInstead = ::useManualInstead,
                            onOpenAutostart = ::openXiaomiAutostart,
                            onPause = { sendControl(CaptureForegroundService.ACTION_PAUSE) },
                            onResume = { sendControl(CaptureForegroundService.ACTION_RESUME) },
                            onStop = {
                                sendControl(CaptureForegroundService.ACTION_STOP)
                                capturing = false
                                refreshChecks()
                            },
                            onUsbTransfer = ::prepareUsbTransfer,
                            onEndpointChanged = { lanEndpoint = it },
                            onSecretChanged = { lanSecret = it },
                            onLanTransfer = ::transferLan,
                        )
                    },
                    onImport = { importLauncher.launch(arrayOf("application/zip", "application/json", "*/*")) },
                    onExport = ::exportStudy,
                    onOpenFenbi = ::openAlreadyLoggedInFenbi,
                    onGoCapture = { tab = AppTab.CAPTURE },
                    message = mineMessage,
                )
            }
        }
    }

    override fun onResume() {
        super.onResume()
        PermissionCoachOverlay.hide(this)
        refreshChecks()
        continuePendingStart()
    }

    private fun refreshChecks() {
        overlayReady = Settings.canDrawOverlays(this)
        accessibilityReady = isAutomationEnabled()
        val task = activeTask ?: store.listTasks().firstOrNull()
        val state = task?.let { store.loadSession(it.id) }
        frameCount = state?.savedPaths?.size ?: 0
        syncCaptures()
        library = studyStore.load()
        if (capturing) return
        taskStatus = when {
            frameCount > 0 -> "这套卷已拍完，可传到电脑识别，或继续在本机复习已导入的题"
            else -> "在已经登录的粉笔里打开已完成试卷"
        }
    }

    private fun syncCaptures() {
        store.listTasks().forEach { task ->
            val session = store.loadSession(task.id) ?: return@forEach
            if (session.savedPaths.isEmpty()) return@forEach
            studyStore.upsertPaper(
                StudyPaper(task.id, task.title, "fenbi-capture", task.createdAtEpochMs, session.savedPaths.size),
            )
        }
    }

    private fun markQuestion(question: StudyQuestion, correct: Boolean) {
        val updated = question.copy(
            isCorrect = correct,
            wrongCount = if (correct) 0 else question.wrongCount + 1,
        )
        library = studyStore.replaceQuestion(updated)
        selectedQuestion = updated
    }

    private fun saveQuestion(question: StudyQuestion) {
        library = studyStore.replaceQuestion(question)
        selectedQuestion = question
        mineMessage = "已保存校对"
    }

    private fun deleteQuestion(question: StudyQuestion) {
        library = studyStore.deleteQuestion(question.id)
        selectedQuestion = null
        mineMessage = "已删除 1 题"
    }

    private fun exportStudy(kind: StudyExport) {
        if (library.questions.isEmpty()) {
            Toast.makeText(this, "还没有题目可导出，先导入或等电脑识别后把试卷 JSON 导回来", Toast.LENGTH_LONG).show()
            return
        }
        runCatching {
            when (kind) {
                StudyExport.WRONG_ZIP -> shareFile(JinzhiPackageIo.exportZip(library, File(cacheDir, "今知错题包.zip"), onlyWrong = true), "application/zip", "导出错题包")
                StudyExport.ALL_ZIP -> shareFile(JinzhiPackageIo.exportZip(library, File(cacheDir, "今知全部题目.zip"), onlyWrong = false), "application/zip", "导出全部题目")
                StudyExport.HTML -> {
                    val file = File(cacheDir, "错题卷.html")
                    file.writeText(WrongPaperHtml.render(library, onlyWrong = true), Charsets.UTF_8)
                    shareFile(file, "text/html", "导出错题卷")
                }
            }
            mineMessage = "已生成导出文件"
        }.onFailure { mineMessage = "导出失败：${it.message}" }
    }

    private fun shareFile(file: File, type: String, title: String) {
        val uri = FileProvider.getUriForFile(this, "$packageName.files", file)
        startActivity(
            Intent.createChooser(
                Intent(Intent.ACTION_SEND).apply {
                    this.type = type
                    putExtra(Intent.EXTRA_STREAM, uri)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                },
                title,
            ),
        )
    }

    private fun createTaskAndRequestProjection() {
        pendingStart = true
        tab = AppTab.CAPTURE
        if (!Settings.canDrawOverlays(this)) {
            Toast.makeText(this, "先打开「显示悬浮窗」，打开后会自动继续", Toast.LENGTH_LONG).show()
            openOverlayPermission()
            return
        }
        if (selectedMode != CaptureMode.MANUAL && !isAutomationEnabled()) {
            Toast.makeText(this, "正在进入「${VendorGuide.SERVICE_LABEL}」开关页，打开后按返回就会开始", Toast.LENGTH_LONG).show()
            openAccessibilityToggle()
            return
        }
        pendingStart = false
        launchProjection()
    }

    private fun continuePendingStart() {
        if (!pendingStart) return
        if (!Settings.canDrawOverlays(this)) return
        if (selectedMode != CaptureMode.MANUAL && !isAutomationEnabled()) return
        pendingStart = false
        launchProjection()
    }

    private fun openAlreadyLoggedInFenbi() {
        if (!FenbiAppGuard.launchInstalledFenbi(this)) {
            Toast.makeText(this, "没找到粉笔官方 App。本软件不会替你登录。", Toast.LENGTH_LONG).show()
        }
    }

    private fun launchProjection() {
        val id = UUID.randomUUID().toString()
        val root = getExternalFilesDir(null) ?: filesDir
        val task = CaptureTask(
            id = id,
            title = "粉笔已完成试卷",
            mode = selectedMode,
            createdAtEpochMs = System.currentTimeMillis(),
            outputDirectory = File(root, "capture_sessions/$id/raw").absolutePath,
        )
        activeTask = task
        store.saveTask(task)
        val manager = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        projectionLauncher.launch(manager.createScreenCaptureIntent())
    }

    private fun isAutomationEnabled(): Boolean {
        val expected = ComponentName(this, AutomationAccessibilityService::class.java).flattenToString()
        val enabled = Settings.Secure.getString(contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES).orEmpty()
        return enabled.split(':').any { it.equals(expected, ignoreCase = true) }
    }

    private fun openOverlayPermission() {
        startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
    }

    private fun openAccessibilityToggle() {
        PermissionCoachOverlay.show(this)
        val intents = VendorGuide.accessibilityIntents(VendorGuide.serviceComponent(this))
        val picked = VendorGuide.firstLaunchable(this, intents)
        if (picked != null) {
            try {
                accessibilityLauncher.launch(picked)
                return
            } catch (_: Exception) {
            }
        }
        if (!VendorGuide.openAccessibilityToggle(this)) {
            PermissionCoachOverlay.hide(this)
            Toast.makeText(this, "打不开开关页，请用「打开无障碍列表」或去设置里搜索「${VendorGuide.SERVICE_LABEL}」", Toast.LENGTH_LONG).show()
        }
    }

    private fun openAccessibilityList() {
        if (!VendorGuide.openAccessibilityList(this)) {
            Toast.makeText(this, "请打开系统设置，搜索「无障碍」", Toast.LENGTH_LONG).show()
        }
    }

    private fun copyAccessibilityName() {
        VendorGuide.copyServiceName(this)
        Toast.makeText(this, "已复制「${VendorGuide.SERVICE_LABEL}」。打开系统设置，右上角粘贴搜索。", Toast.LENGTH_LONG).show()
    }

    private fun useManualInstead() {
        selectedMode = CaptureMode.MANUAL
        Toast.makeText(this, "已改成「我自己翻」。你点下一题，我只截图。", Toast.LENGTH_LONG).show()
        if (Settings.canDrawOverlays(this)) {
            launchProjection()
        } else {
            openOverlayPermission()
        }
    }

    private fun openXiaomiAutostart() {
        if (!VendorGuide.openXiaomiAutostart(this)) {
            Toast.makeText(this, "请到设置 → 应用设置 → 丁真笔记本 → 自启动，打开允许。", Toast.LENGTH_LONG).show()
        }
    }

    private fun sendControl(action: String) {
        startService(Intent(this, CaptureForegroundService::class.java).setAction(action))
    }

    private fun selectedTaskAndState(): Pair<CaptureTask, CaptureSessionState>? {
        val task = activeTask ?: store.listTasks().firstOrNull()
        val state = task?.let { store.loadSession(it.id) }
        if (task == null || state == null) {
            Toast.makeText(this, "还没有可传输的采集", Toast.LENGTH_SHORT).show()
            return null
        }
        return task to state
    }

    private fun prepareUsbTransfer() {
        val (task, state) = selectedTaskAndState() ?: return
        transferStatus = "正在准备导出…"
        thread(name = "fenbi-usb-transfer") {
            runCatching {
                val target = File(getExternalFilesDir(null) ?: filesDir, "usb_exports")
                val updated = UsbTransferClient(target).transfer(task, state)
                store.saveSession(updated)
                target.absolutePath
            }.onSuccess { path ->
                runOnUiThread {
                    transferStatus = "已导出到手机，可用 USB 拷到电脑"
                    shareExportedFolder(File(path, task.id))
                }
            }.onFailure { error -> runOnUiThread { transferStatus = "导出失败：${error.message}" } }
        }
    }

    private fun shareExportedFolder(folder: File) {
        val images = folder.listFiles()?.filter { it.extension.equals("png", true) }.orEmpty()
        if (images.isEmpty()) return
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, "采集导出目录：${folder.absolutePath}")
        }
        runCatching { startActivity(Intent.createChooser(intent, "分享导出路径")) }
    }

    private fun transferLan() {
        val (task, state) = selectedTaskAndState() ?: return
        val paired = parsePairingCode(lanEndpoint)
        val endpoint = paired?.first ?: runCatching { URL(lanEndpoint.trim()) }.getOrNull()
        val secretSource = paired?.second ?: lanSecret.toByteArray(Charsets.UTF_8)
        if (endpoint == null || secretSource.size < 16) {
            transferStatus = "请粘贴电脑上的配对码"
            return
        }
        val secret = secretSource.copyOf()
        lanSecret = ""
        transferStatus = "正在传到电脑…"
        thread(name = "fenbi-lan-transfer") {
            runCatching {
                val updated = LanTransferClient(endpoint, secret).transfer(task, state)
                secret.fill(0)
                store.saveSession(updated)
                updated.lastTransferredSequence
            }.onSuccess { sequence ->
                runOnUiThread { transferStatus = "已传到电脑（$sequence）。识别后把试卷 JSON 或错题包导回手机。" }
            }.onFailure { error ->
                secret.fill(0)
                runOnUiThread { transferStatus = "传输失败：${error.message}" }
            }
        }
    }

    private fun isZip(file: File): Boolean {
        if (!file.exists() || file.length() < 4) return false
        val header = ByteArray(2)
        val read = file.inputStream().use { it.read(header) }
        return read == 2 && header[0] == 0x50.toByte() && header[1] == 0x4B.toByte()
    }
}
