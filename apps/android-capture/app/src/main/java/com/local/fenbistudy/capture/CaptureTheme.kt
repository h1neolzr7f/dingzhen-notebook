package com.local.fenbistudy.capture

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val Teal = Color(0xFF0F766E)
val TealDark = Color(0xFF115E59)
val Coral = Color(0xFFE86B4A)
val Cream = Color(0xFFF7F3EC)
val CardWhite = Color(0xFFFFFFFF)
val Ink = Color(0xFF1F2933)
val InkMuted = Color(0xFF6B7280)
val SoftGreen = Color(0xFFECFDF5)
val SoftAmber = Color(0xFFFFF7ED)

private val JinzhiColors = lightColorScheme(
    primary = Teal,
    onPrimary = Color.White,
    secondary = Coral,
    onSecondary = Color.White,
    background = Cream,
    onBackground = Ink,
    surface = CardWhite,
    onSurface = Ink,
    surfaceVariant = Color(0xFFF0E8DC),
    onSurfaceVariant = InkMuted,
    outline = Color(0xFFD6CBBA),
)

@Composable
fun JinzhiCaptureTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = JinzhiColors, content = content)
}
