package com.local.fenbistudy.capture

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun JinzhiStudyApp(
    library: StudyLibrary,
    tab: AppTab,
    onTab: (AppTab) -> Unit,
    selectedQuestion: StudyQuestion?,
    onOpenQuestion: (StudyQuestion) -> Unit,
    onCloseQuestion: () -> Unit,
    onMarkQuestion: (StudyQuestion, Boolean) -> Unit,
    onSaveQuestion: (StudyQuestion) -> Unit,
    onDeleteQuestion: (StudyQuestion) -> Unit,
    reviewStage: ReviewStage,
    onReviewStage: (ReviewStage) -> Unit,
    capture: @Composable () -> Unit,
    onImport: () -> Unit,
    onExport: (StudyExport) -> Unit,
    onOpenFenbi: () -> Unit,
    onGoCapture: () -> Unit,
    message: String,
) {
    var browse by remember { mutableStateOf(StudyBrowse()) }
    var session by remember { mutableStateOf<List<StudyQuestion>>(emptyList()) }
    var sessionIndex by remember { mutableStateOf(0) }

    fun openFiltered(next: StudyBrowse, target: AppTab = AppTab.MISTAKES) {
        browse = next
        onCloseQuestion()
        onTab(target)
    }

    fun startSession(items: List<StudyQuestion>) {
        session = items
        sessionIndex = 0
        items.firstOrNull()?.let(onOpenQuestion)
    }

    fun advanceSession() {
        if (session.isEmpty()) return
        val next = sessionIndex + 1
        if (next >= session.size) {
            session = emptyList()
            onCloseQuestion()
        } else {
            sessionIndex = next
            onOpenQuestion(session[next])
        }
    }

    Scaffold(
        containerColor = Cream,
        bottomBar = {
            NavigationBar(containerColor = CardWhite) {
                AppTab.entries.forEach { item ->
                    NavigationBarItem(
                        selected = tab == item,
                        onClick = { onTab(item); onCloseQuestion() },
                        icon = { Text(item.icon, fontSize = 16.sp) },
                        label = { Text(item.label, fontSize = 11.sp) },
                        colors = NavigationBarItemDefaults.colors(indicatorColor = SoftGreen),
                    )
                }
            }
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            when {
                selectedQuestion != null -> QuestionDetail(
                    question = selectedQuestion,
                    sessionLabel = if (session.isNotEmpty()) "复习 ${sessionIndex + 1}/${session.size}" else "",
                    onBack = { session = emptyList(); onCloseQuestion() },
                    onRight = { onMarkQuestion(selectedQuestion, true); advanceSession() },
                    onWrong = { onMarkQuestion(selectedQuestion, false); advanceSession() },
                    onSave = onSaveQuestion,
                    onDelete = { onDeleteQuestion(selectedQuestion); session = emptyList() },
                    onNext = { advanceSession() },
                )
                tab == AppTab.HOME -> HomeScreen(
                    library = library,
                    onOpenQuestion = onOpenQuestion,
                    onGoCapture = onGoCapture,
                    onOpenFenbi = onOpenFenbi,
                    onOpenPaper = { paper -> openFiltered(StudyBrowse(paperId = paper.id, onlyWrong = false)) },
                    onOpenKnowledge = { point -> openFiltered(StudyBrowse(knowledge = point, onlyWrong = true)) },
                    onTab = onTab,
                )
                tab == AppTab.CAPTURE -> capture()
                tab == AppTab.MISTAKES -> MistakesScreen(
                    library = library,
                    browse = browse,
                    onBrowse = { browse = it },
                    onOpenQuestion = onOpenQuestion,
                )
                tab == AppTab.REVIEW -> ReviewScreen(
                    library = library,
                    stage = reviewStage,
                    onStage = onReviewStage,
                    onOpenQuestion = onOpenQuestion,
                    onStartSession = { startSession(it) },
                    onOpenKnowledge = { point ->
                        onReviewStage(ReviewStage.FIRST)
                        openFiltered(StudyBrowse(knowledge = point, onlyWrong = true), AppTab.MISTAKES)
                    },
                )
                tab == AppTab.MINE -> MineScreen(library, message, onImport, onExport, onOpenFenbi)
            }
        }
    }
}

private val AppTab.icon: String
    get() = when (this) {
        AppTab.HOME -> "●"
        AppTab.CAPTURE -> "＋"
        AppTab.MISTAKES -> "题"
        AppTab.REVIEW -> "复"
        AppTab.MINE -> "我"
    }

@Composable
private fun HomeScreen(
    library: StudyLibrary,
    onOpenQuestion: (StudyQuestion) -> Unit,
    onGoCapture: () -> Unit,
    onOpenFenbi: () -> Unit,
    onOpenPaper: (StudyPaper) -> Unit,
    onOpenKnowledge: (String) -> Unit,
    onTab: (AppTab) -> Unit,
) {
    val grouped = ReviewPlanner.group(library.questions)
    Column(Modifier.fillMaxSize().background(Cream).verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("丁真笔记本", fontWeight = FontWeight.SemiBold, fontSize = 26.sp, color = Ink)
        Text("手机端就是完整错题本：收题、校对、错题、复习、组卷、导入导出。本软件不登录粉笔。", color = InkMuted, fontSize = 13.sp)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            StatChip("错题", library.wrong.size.toString(), Modifier.weight(1f))
            StatChip("待复习", library.dueToday.size.toString(), Modifier.weight(1f))
            StatChip("已掌握", library.mastered.size.toString(), Modifier.weight(1f))
            StatChip("试卷", library.papers.size.toString(), Modifier.weight(1f))
        }
        Button(
            onClick = onGoCapture,
            modifier = Modifier.fillMaxWidth().height(50.dp),
            shape = RoundedCornerShape(16.dp),
            colors = ButtonDefaults.buttonColors(Teal),
        ) { Text("去粉笔收题", fontWeight = FontWeight.SemiBold) }
        OutlinedButton(onClick = onOpenFenbi, modifier = Modifier.fillMaxWidth().height(46.dp), shape = RoundedCornerShape(16.dp)) {
            Text("打开已经登录的粉笔")
        }
        Section("今日复习") {
            val today = (grouped[ReviewStage.PREVIEW].orEmpty() + grouped[ReviewStage.FIRST].orEmpty()).take(6)
            if (today.isEmpty()) {
                Text("还没有待复习的题。先收题或导入错题包。", color = InkMuted, fontSize = 13.sp)
            } else {
                today.forEach { QuestionRow(it, onOpenQuestion) }
                TextButton(onClick = { onTab(AppTab.REVIEW) }) { Text("查看全部复习") }
            }
        }
        Section("试卷") {
            if (library.papers.isEmpty()) {
                Text("导入今知错题包，或从粉笔采集一套卷。题干识别可在电脑完成后把试卷 JSON 导回。", color = InkMuted, fontSize = 13.sp)
            } else {
                library.papers.take(12).forEach { paper ->
                    val count = library.questions.count { it.paperId == paper.id }
                    val pending = if (paper.pendingFrames > 0 && count == 0) " · 待识别 ${paper.pendingFrames} 张" else ""
                    Text(
                        "${paper.title} · ${if (count > 0) "${count} 题" else "还没有结构化题目"}$pending",
                        modifier = Modifier.fillMaxWidth().clickable { onOpenPaper(paper) }.padding(vertical = 6.dp),
                        color = Ink,
                    )
                }
            }
        }
        Section("薄弱知识点") {
            val weak = ReviewPlanner.knowledgeTree(library.wrong).entries.sortedByDescending { it.value.size }.take(8)
            if (weak.isEmpty()) Text("做完几道错题后，这里会列出薄弱点。", color = InkMuted, fontSize = 13.sp)
            else weak.forEach { (name, items) ->
                Text(
                    "$name · ${items.size} 道",
                    modifier = Modifier.fillMaxWidth().clickable { onOpenKnowledge(name) }.padding(vertical = 4.dp),
                    color = Ink,
                    fontSize = 14.sp,
                )
            }
        }
    }
}

@Composable
private fun MistakesScreen(
    library: StudyLibrary,
    browse: StudyBrowse,
    onBrowse: (StudyBrowse) -> Unit,
    onOpenQuestion: (StudyQuestion) -> Unit,
) {
    val items = StudyFilters.apply(library, browse)
    val folders = StudyFilters.folders(library)
    val knowledge = StudyFilters.knowledge(library)
    Column(Modifier.fillMaxSize().background(Cream).verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("错题本", fontWeight = FontWeight.SemiBold, fontSize = 24.sp, color = Ink)
        OutlinedTextField(
            value = browse.query,
            onValueChange = { onBrowse(browse.copy(query = it)) },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
            placeholder = { Text("搜索题干、答案、解析、知识点") },
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip("只看错题", browse.onlyWrong) { onBrowse(browse.copy(onlyWrong = true)) }
            FilterChip("全部题目", !browse.onlyWrong) { onBrowse(browse.copy(onlyWrong = false)) }
        }
        if (library.papers.isNotEmpty()) {
            ChipRow {
                FilterChip("全部试卷", browse.paperId == null) { onBrowse(browse.copy(paperId = null)) }
                library.papers.forEach { paper ->
                    FilterChip(paper.title.take(10), browse.paperId == paper.id) { onBrowse(browse.copy(paperId = paper.id)) }
                }
            }
        }
        if (folders.size > 1) {
            ChipRow {
                FilterChip("全部分类", browse.folder == null) { onBrowse(browse.copy(folder = null)) }
                folders.forEach { folder ->
                    FilterChip(folder.take(10), browse.folder == folder) { onBrowse(browse.copy(folder = folder)) }
                }
            }
        }
        if (knowledge.isNotEmpty()) {
            ChipRow {
                FilterChip("全部知识点", browse.knowledge == null) { onBrowse(browse.copy(knowledge = null)) }
                knowledge.forEach { point ->
                    FilterChip(point.take(10), browse.knowledge == point) { onBrowse(browse.copy(knowledge = point)) }
                }
            }
        }
        Text("共 ${items.size} 题", color = InkMuted, fontSize = 12.sp)
        if (items.isEmpty()) {
            Text("还没有题目。去收题，或在「我的」里导入今知错题包 / 试卷 JSON。", color = InkMuted)
        } else {
            items.forEach { QuestionRow(it, onOpenQuestion) }
        }
    }
}

@Composable
private fun ReviewScreen(
    library: StudyLibrary,
    stage: ReviewStage,
    onStage: (ReviewStage) -> Unit,
    onOpenQuestion: (StudyQuestion) -> Unit,
    onStartSession: (List<StudyQuestion>) -> Unit,
    onOpenKnowledge: (String) -> Unit,
) {
    val grouped = ReviewPlanner.group(library.questions)
    val tree = ReviewPlanner.knowledgeTree(library.questions)
    val current = grouped[stage].orEmpty()
    Column(Modifier.fillMaxSize().background(Cream).verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("复习计划", fontWeight = FontWeight.SemiBold, fontSize = 24.sp, color = Ink)
        Text("预习 / 一刷 / 二刷 / 间隔 / 已掌握，和今知同一套本地轨道。", color = InkMuted, fontSize = 13.sp)
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
            ReviewStage.entries.forEach { item ->
                FilterChip("${item.title}${grouped[item].orEmpty().size}", stage == item, Modifier.weight(1f)) { onStage(item) }
            }
        }
        if (current.isNotEmpty()) {
            Button(
                onClick = { onStartSession(current) },
                modifier = Modifier.fillMaxWidth().height(48.dp),
                shape = RoundedCornerShape(14.dp),
                colors = ButtonDefaults.buttonColors(Teal),
            ) { Text("开始${stage.title}（${current.size}题）") }
        } else {
            Text("这条轨道暂时没有题。", color = InkMuted)
        }
        current.forEach { QuestionRow(it, onOpenQuestion) }
        Section("知识点导图") {
            if (tree.isEmpty()) Text("有题目后按知识点归类。", color = InkMuted, fontSize = 13.sp)
            else tree.forEach { (name, items) ->
                Text(
                    "$name · ${items.size} 道",
                    modifier = Modifier.fillMaxWidth().clickable { onOpenKnowledge(name) },
                    fontWeight = FontWeight.SemiBold,
                    color = TealDark,
                )
                items.take(4).forEach { Text("· 第${it.sequence}题 ${it.stem.take(28)}", color = Ink, fontSize = 13.sp) }
            }
        }
    }
}

@Composable
private fun MineScreen(
    library: StudyLibrary,
    message: String,
    onImport: () -> Unit,
    onExport: (StudyExport) -> Unit,
    onOpenFenbi: () -> Unit,
) {
    Column(Modifier.fillMaxSize().background(Cream).verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("我的", fontWeight = FontWeight.SemiBold, fontSize = 24.sp, color = Ink)
        Section("错题包") {
            Text("兼容今知错题包 ZIP，也支持本工具导出的试卷 JSON。", color = InkMuted, fontSize = 13.sp)
            Button(onClick = onImport, modifier = Modifier.fillMaxWidth().height(48.dp), shape = RoundedCornerShape(14.dp), colors = ButtonDefaults.buttonColors(Teal)) {
                Text("导入错题包 / 试卷")
            }
            OutlinedButton(onClick = { onExport(StudyExport.WRONG_ZIP) }, modifier = Modifier.fillMaxWidth().height(48.dp), shape = RoundedCornerShape(14.dp)) {
                Text("导出错题包")
            }
            OutlinedButton(onClick = { onExport(StudyExport.ALL_ZIP) }, modifier = Modifier.fillMaxWidth().height(48.dp), shape = RoundedCornerShape(14.dp)) {
                Text("导出全部题目")
            }
            Text("${library.questions.size} 题 · ${library.papers.size} 套卷 · 错题 ${library.wrong.size}", color = InkMuted, fontSize = 13.sp)
            if (message.isNotBlank()) Text(message, color = TealDark, fontSize = 13.sp)
        }
        Section("组卷") {
            Text("本机生成错题卷和答题卡 HTML，可打印或发到电脑。", color = InkMuted, fontSize = 13.sp)
            Button(onClick = { onExport(StudyExport.HTML) }, modifier = Modifier.fillMaxWidth().height(48.dp), shape = RoundedCornerShape(14.dp), colors = ButtonDefaults.buttonColors(Teal)) {
                Text("导出错题卷 / 答题卡")
            }
        }
        Section("粉笔") {
            Text("本软件不登录粉笔，也不要账号密码。", color = InkMuted, fontSize = 13.sp)
            OutlinedButton(onClick = onOpenFenbi, modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(14.dp)) {
                Text("打开已经登录的粉笔")
            }
        }
        Section("关于") {
            Text("丁真笔记本 1.3.4 · 收题、校对、错题、复习、组卷、导入导出都在这台手机。数据只在本机。", color = InkMuted, fontSize = 13.sp)
        }
    }
}

@Composable
private fun QuestionDetail(
    question: StudyQuestion,
    sessionLabel: String,
    onBack: () -> Unit,
    onRight: () -> Unit,
    onWrong: () -> Unit,
    onSave: (StudyQuestion) -> Unit,
    onDelete: () -> Unit,
    onNext: () -> Unit,
) {
    var editing by remember(question.id) { mutableStateOf(false) }
    var stem by remember(question.id) { mutableStateOf(question.stem) }
    var userAnswer by remember(question.id) { mutableStateOf(question.userAnswer) }
    var officialAnswer by remember(question.id) { mutableStateOf(question.officialAnswer) }
    var explanation by remember(question.id) { mutableStateOf(question.explanation) }
    var confirmDelete by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxSize().background(Cream).verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack) { Text("返回") }
            if (sessionLabel.isNotBlank()) Text(sessionLabel, color = TealDark, fontSize = 13.sp)
        }
        Text("${question.folderName} · 第${question.sequence}题 · ${ReviewPlanner.stage(question).title}", color = InkMuted, fontSize = 13.sp)
        if (editing) {
            OutlinedTextField(stem, { stem = it }, modifier = Modifier.fillMaxWidth(), label = { Text("题干") }, minLines = 3)
            OutlinedTextField(userAnswer, { userAnswer = it }, modifier = Modifier.fillMaxWidth(), label = { Text("我的答案") })
            OutlinedTextField(officialAnswer, { officialAnswer = it }, modifier = Modifier.fillMaxWidth(), label = { Text("正确答案") })
            OutlinedTextField(explanation, { explanation = it }, modifier = Modifier.fillMaxWidth(), label = { Text("解析") }, minLines = 3)
            Button(
                onClick = {
                    onSave(question.copy(stem = stem, userAnswer = userAnswer, officialAnswer = officialAnswer, explanation = explanation))
                    editing = false
                },
                modifier = Modifier.fillMaxWidth().height(48.dp),
                shape = RoundedCornerShape(14.dp),
                colors = ButtonDefaults.buttonColors(Teal),
            ) { Text("保存校对") }
        } else {
            Text(question.stem.ifBlank { "（无题干，可点校对补上，或到电脑识别后导入）" }, fontWeight = FontWeight.SemiBold, fontSize = 18.sp, color = Ink)
            Section("我的答案") { Text(question.userAnswer.ifBlank { "未作答" }, color = Ink) }
            Section("正确答案") { Text(question.officialAnswer.ifBlank { "未采集" }, color = TealDark, fontWeight = FontWeight.SemiBold) }
            Section("解析") { Text(question.explanation.ifBlank { "还没有解析" }, color = Ink) }
            if (question.knowledge.isNotEmpty()) Section("知识点") { Text(question.knowledge.joinToString("、"), color = Ink) }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            Button(onClick = onRight, modifier = Modifier.weight(1f).height(48.dp), shape = RoundedCornerShape(14.dp), colors = ButtonDefaults.buttonColors(Teal)) { Text("这题会了") }
            Button(onClick = onWrong, modifier = Modifier.weight(1f).height(48.dp), shape = RoundedCornerShape(14.dp), colors = ButtonDefaults.buttonColors(Coral)) { Text("还是错了") }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            OutlinedButton(onClick = { editing = !editing }, modifier = Modifier.weight(1f), shape = RoundedCornerShape(14.dp)) {
                Text(if (editing) "取消校对" else "校对这题")
            }
            if (sessionLabel.isNotBlank()) {
                OutlinedButton(onClick = onNext, modifier = Modifier.weight(1f), shape = RoundedCornerShape(14.dp)) { Text("下一题") }
            } else {
                OutlinedButton(onClick = { confirmDelete = true }, modifier = Modifier.weight(1f), shape = RoundedCornerShape(14.dp)) { Text("删除") }
            }
        }
        Text("会了进入已掌握；错了进入一刷/二刷/间隔。", color = InkMuted, fontSize = 12.sp)
    }
    if (confirmDelete) {
        AlertDialog(
            onDismissRequest = { confirmDelete = false },
            title = { Text("删除这道题？") },
            text = { Text("只从本机错题本删除，粉笔官方 App 里的试卷不会动。") },
            confirmButton = { TextButton(onClick = { confirmDelete = false; onDelete() }) { Text("删除") } },
            dismissButton = { TextButton(onClick = { confirmDelete = false }) { Text("取消") } },
        )
    }
}

@Composable
private fun QuestionRow(question: StudyQuestion, onOpen: (StudyQuestion) -> Unit) {
    val mark = when (question.isCorrect) {
        true -> "会"
        false -> "错"
        null -> "待"
    }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(CardWhite)
            .clickable { onOpen(question) }
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text("第${question.sequence}题 · ${ReviewPlanner.stage(question).title} · ${question.folderName}", color = InkMuted, fontSize = 12.sp)
            Text(question.stem.ifBlank { question.folderName }.take(42), color = Ink, fontSize = 14.sp)
        }
        Text(mark, color = if (question.isCorrect == false) Coral else TealDark, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun Section(title: String, content: @Composable ColumnScope.() -> Unit) {
    Card(
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(CardWhite),
        elevation = CardDefaults.cardElevation(0.dp),
        modifier = Modifier.fillMaxWidth().border(1.dp, androidx.compose.ui.graphics.Color(0x33D6CBBA), RoundedCornerShape(20.dp)),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, fontWeight = FontWeight.SemiBold, color = Ink)
            content()
        }
    }
}

@Composable
private fun StatChip(label: String, value: String, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.clip(RoundedCornerShape(16.dp)).background(CardWhite).padding(vertical = 12.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(value, fontWeight = FontWeight.Bold, fontSize = 20.sp, color = TealDark)
        Text(label, color = InkMuted, fontSize = 11.sp)
    }
}

@Composable
private fun ChipRow(content: @Composable () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) { content() }
}

@Composable
private fun FilterChip(label: String, selected: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(12.dp))
            .background(if (selected) Teal else ColorCreamSoft)
            .clickable(onClick = onClick)
            .padding(horizontal = 8.dp, vertical = 8.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = if (selected) CardWhite else Ink, fontSize = 11.sp, fontWeight = FontWeight.Medium)
    }
}

private val ColorCreamSoft = androidx.compose.ui.graphics.Color(0xFFF0E8DC)
