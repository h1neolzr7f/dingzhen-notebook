package com.local.fenbistudy.capture

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

fun CaptureMode.label(): String = when (this) {
    CaptureMode.MANUAL -> "我自己翻"
    CaptureMode.SEMI_AUTO -> "帮我滑"
    CaptureMode.AUTO -> "自动翻页"
}

fun CaptureMode.hint(): String = when (this) {
    CaptureMode.MANUAL -> "你点下一题，我只截图"
    CaptureMode.SEMI_AUTO -> "我帮你滑完解析"
    CaptureMode.AUTO -> "齐了就进下一题"
}

@Composable
fun CaptureHome(
    selectedMode: CaptureMode,
    taskStatus: String,
    frameCount: Int,
    capturing: Boolean,
    overlayReady: Boolean,
    accessibilityReady: Boolean,
    vendorFamily: VendorFamily,
    lanEndpoint: String,
    lanSecret: String,
    transferStatus: String,
    onModeSelected: (CaptureMode) -> Unit,
    onStart: () -> Unit,
    onOpenFenbi: () -> Unit,
    onOverlayPermission: () -> Unit,
    onOpenAccessibilityToggle: () -> Unit,
    onOpenAccessibilityList: () -> Unit,
    onCopyServiceName: () -> Unit,
    onUseManualInstead: () -> Unit,
    onOpenAutostart: () -> Unit,
    onPause: () -> Unit,
    onResume: () -> Unit,
    onStop: () -> Unit,
    onUsbTransfer: () -> Unit,
    onEndpointChanged: (String) -> Unit,
    onSecretChanged: (String) -> Unit,
    onLanTransfer: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Cream)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 18.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                modifier = Modifier
                    .size(42.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(Teal),
                contentAlignment = Alignment.Center,
            ) {
                Text("知", color = CardWhite, fontWeight = FontWeight.Bold, fontSize = 20.sp)
            }
            Column(Modifier.padding(start = 12.dp)) {
                Text("丁真笔记本", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.SemiBold, color = Ink)
                Text("在已经登录的粉笔里收题", color = InkMuted, fontSize = 13.sp)
            }
        }

        Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(SoftGreen), elevation = CardDefaults.cardElevation(0.dp)) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("三步收题", fontWeight = FontWeight.SemiBold, color = TealDark)
                StepRow("1", "打开粉笔里已完成的试卷")
                StepRow("2", "点开始，回到粉笔自动采集")
                StepRow("3", "传到电脑，自动识别校对")
                Text("本软件不登录粉笔，也不要账号密码。", color = InkMuted, fontSize = 12.sp)
            }
        }

        SectionCard("准备") {
            PermissionRow("悬浮窗", "采集时显示控制条", overlayReady, if (overlayReady) "已开启" else "去开启", onOverlayPermission)
            if (accessibilityReady) {
                PermissionRow("自动翻页", "已打开「${VendorGuide.SERVICE_LABEL}」", true, "已开启") {}
            } else {
                AccessibilityCoach(
                    family = vendorFamily,
                    onOpenToggle = onOpenAccessibilityToggle,
                    onOpenList = onOpenAccessibilityList,
                    onCopyName = onCopyServiceName,
                    onUseManual = onUseManualInstead,
                    onOpenAutostart = onOpenAutostart,
                )
            }
        }

        SectionCard("怎么采") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                CaptureMode.entries.forEach { mode ->
                    ModeChip(
                        mode = mode,
                        selected = selectedMode == mode,
                        modifier = Modifier.weight(1f),
                        onClick = { onModeSelected(mode) },
                    )
                }
            }
        }

        Button(
            onClick = onStart,
            modifier = Modifier.fillMaxWidth().height(52.dp),
            shape = RoundedCornerShape(16.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Teal, contentColor = CardWhite),
        ) {
            Text(if (capturing) "采集中，请留在粉笔" else "开始采集，回到粉笔", fontWeight = FontWeight.SemiBold)
        }
        OutlinedButton(
            onClick = onOpenFenbi,
            modifier = Modifier.fillMaxWidth().height(48.dp),
            shape = RoundedCornerShape(16.dp),
        ) { Text("打开已经登录的粉笔") }

        SectionCard("本次试卷") {
            Text(taskStatus, color = Ink, fontSize = 14.sp)
            Text(if (frameCount > 0) "已拍 $frameCount 张" else "还没有截图", color = InkMuted, fontSize = 13.sp)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                OutlinedButton(onClick = onPause, modifier = Modifier.weight(1f), enabled = capturing, shape = RoundedCornerShape(12.dp)) { Text("暂停") }
                OutlinedButton(onClick = onResume, modifier = Modifier.weight(1f), enabled = capturing, shape = RoundedCornerShape(12.dp)) { Text("继续") }
                Button(
                    onClick = onStop,
                    modifier = Modifier.weight(1f),
                    enabled = capturing,
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Coral),
                ) { Text("结束") }
            }
        }

        SectionCard("传到电脑") {
            Text("电脑点「手机无线传入」，把配对码贴在这里。同一 Wi-Fi。", color = InkMuted, fontSize = 13.sp)
            OutlinedTextField(
                value = lanEndpoint,
                onValueChange = onEndpointChanged,
                label = { Text("配对码") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                shape = RoundedCornerShape(14.dp),
                colors = OutlinedTextFieldDefaults.colors(focusedContainerColor = Cream, unfocusedContainerColor = Cream),
            )
            OutlinedTextField(
                value = lanSecret,
                onValueChange = onSecretChanged,
                label = { Text("密钥（配对码里有可留空）") },
                modifier = Modifier.fillMaxWidth(),
                visualTransformation = PasswordVisualTransformation(),
                singleLine = true,
                shape = RoundedCornerShape(14.dp),
                colors = OutlinedTextFieldDefaults.colors(focusedContainerColor = Cream, unfocusedContainerColor = Cream),
            )
            Button(
                onClick = onLanTransfer,
                modifier = Modifier.fillMaxWidth().height(48.dp),
                shape = RoundedCornerShape(14.dp),
                colors = ButtonDefaults.buttonColors(containerColor = TealDark),
            ) { Text("传到电脑并识别") }
            TextButton(onClick = onUsbTransfer, modifier = Modifier.align(Alignment.Start)) {
                Text("改用 USB 导出", color = InkMuted)
            }
            Text(transferStatus, color = InkMuted, fontSize = 12.sp)
        }
        Spacer(Modifier.height(12.dp))
    }
}

@Composable
private fun SectionCard(title: String, content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit) {
    Card(
        shape = RoundedCornerShape(22.dp),
        colors = CardDefaults.cardColors(CardWhite),
        elevation = CardDefaults.cardElevation(0.dp),
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, MaterialTheme.colorScheme.outline.copy(alpha = 0.45f), RoundedCornerShape(22.dp)),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(title, fontWeight = FontWeight.SemiBold, color = Ink)
            content()
        }
    }
}

@Composable
private fun StepRow(number: String, text: String) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Box(
            modifier = Modifier.size(24.dp).clip(CircleShape).background(Teal),
            contentAlignment = Alignment.Center,
        ) { Text(number, color = CardWhite, fontSize = 12.sp, fontWeight = FontWeight.Bold) }
        Text(text, color = Ink, fontSize = 14.sp)
    }
}

@Composable
private fun AccessibilityCoach(
    family: VendorFamily,
    onOpenToggle: () -> Unit,
    onOpenList: () -> Unit,
    onCopyName: () -> Unit,
    onUseManual: () -> Unit,
    onOpenAutostart: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(SoftAmber)
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text("自动翻页还没开", fontWeight = FontWeight.SemiBold, color = Ink)
        Text(VendorGuide.title(family), color = Ink, fontSize = 13.sp)
        Button(
            onClick = onOpenToggle,
            modifier = Modifier.fillMaxWidth().height(52.dp),
            shape = RoundedCornerShape(12.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Teal, contentColor = CardWhite),
        ) { Text("点我进入开关页", fontWeight = FontWeight.SemiBold, fontSize = 16.sp) }
        Text("进去后打开「${VendorGuide.SERVICE_LABEL}」，按返回就会回来。", color = InkMuted, fontSize = 12.sp)
        TextButton(onClick = onUseManual, modifier = Modifier.align(Alignment.Start)) {
            Text("先不用自动翻，我自己点下一题", color = TealDark)
        }
        var more by remember { mutableStateOf(false) }
        TextButton(onClick = { more = !more }, modifier = Modifier.align(Alignment.Start)) {
            Text(if (more) "收起备用入口" else "没自动进去？备用入口", color = InkMuted)
        }
        if (more) {
            Text(VendorGuide.searchHint(), color = InkMuted, fontSize = 12.sp)
            OutlinedButton(onClick = onOpenList, modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp)) {
                Text("打开无障碍列表")
            }
            OutlinedButton(onClick = onCopyName, modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp)) {
                Text("复制名称，去系统设置里搜索")
            }
            if (family == VendorFamily.XIAOMI) {
                OutlinedButton(onClick = onOpenAutostart, modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp)) {
                    Text("小米：再打开自启动")
                }
            }
        }
    }
}

@Composable
private fun PermissionRow(title: String, hint: String, ready: Boolean, action: String, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(if (ready) SoftGreen else SoftAmber)
            .clickable(onClick = onClick)
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(title, fontWeight = FontWeight.Medium, color = Ink)
            Text(hint, color = InkMuted, fontSize = 12.sp)
        }
        Text(if (ready) "已开启" else action, color = if (ready) TealDark else Coral, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
    }
}

@Composable
private fun ModeChip(mode: CaptureMode, selected: Boolean, modifier: Modifier, onClick: () -> Unit) {
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(16.dp))
            .background(if (selected) Teal else ColorCreamSoft)
            .clickable(onClick = onClick)
            .padding(horizontal = 8.dp, vertical = 12.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(mode.label(), color = if (selected) CardWhite else Ink, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
        Text(mode.hint(), color = if (selected) CardWhite.copy(alpha = 0.86f) else InkMuted, fontSize = 10.sp)
    }
}

private val ColorCreamSoft = Color(0xFFF0E8DC)
