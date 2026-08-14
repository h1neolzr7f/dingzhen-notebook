package com.local.fenbistudy.capture

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.provider.Settings
import android.util.TypedValue
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import android.view.WindowManager

/** Compact overlay used while Fenbi is in the foreground. */
class FloatingController(private val context: Context) {
    private val windowManager = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
    private var view: LinearLayout? = null
    private var questionLabel: TextView? = null
    private var statusLabel: TextView? = null
    private var extra: LinearLayout? = null
    private var paused = false

    @Suppress("ClickableViewAccessibility")
    fun show(
        onCapture: () -> Unit,
        onPause: () -> Unit,
        onResume: () -> Unit,
        onMarkQuestion: () -> Unit,
        onMarkAnalysis: () -> Unit,
        onRetry: () -> Unit,
        onSkip: () -> Unit,
        onStop: () -> Unit,
    ): Boolean {
        if (!Settings.canDrawOverlays(context) || view != null) return false
        val density = context.resources.displayMetrics.density
        val container = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            val pad = (12 * density).toInt()
            setPadding(pad, pad, pad, pad)
            background = GradientDrawable().apply {
                setColor(0xF21B2A33.toInt())
                cornerRadius = 22 * density
            }
        }
        TextView(context).apply {
            text = "丁真笔记本"
            setTextColor(0xFF5EEAD4.toInt())
            setTypeface(typeface, Typeface.BOLD)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
        }.also(container::addView)
        questionLabel = TextView(context).apply {
            text = "等待题号"
            setTextColor(Color.WHITE)
            setTypeface(typeface, Typeface.BOLD)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            setPadding(0, (4 * density).toInt(), 0, 0)
        }.also(container::addView)
        statusLabel = TextView(context).apply {
            text = "留在已完成试卷"
            setTextColor(0xFFD1D5DB.toInt())
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            setPadding(0, (2 * density).toInt(), 0, (8 * density).toInt())
        }.also(container::addView)

        val actions = LinearLayout(context).apply { orientation = LinearLayout.HORIZONTAL }
        actions.addView(chip("暂停") { if (paused) onResume() else onPause(); paused = !paused }, chipParams(density))
        actions.addView(chip("结束", 0xFFE86B4A.toInt(), onStop), chipParams(density))
        container.addView(actions)

        extra = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            visibility = View.GONE
            val more = listOf(
                "截图" to onCapture,
                "题目页" to onMarkQuestion,
                "解析页" to onMarkAnalysis,
                "重拍" to onRetry,
                "跳过" to onSkip,
            )
            more.forEach { (label, action) -> addView(chip(label, action = action)) }
        }
        TextView(context).apply {
            text = "更多"
            setTextColor(0xFF9CA3AF.toInt())
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            setPadding(0, (8 * density).toInt(), 0, 0)
            setOnClickListener {
                extra?.visibility = if (extra?.visibility == View.VISIBLE) View.GONE else View.VISIBLE
            }
        }.also(container::addView)
        extra?.let(container::addView)

        val type = WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            type,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            android.graphics.PixelFormat.TRANSLUCENT,
        ).apply { gravity = Gravity.TOP or Gravity.END; x = 16; y = 140 }
        var downX = 0f
        var downY = 0f
        var startX = 0
        var startY = 0
        questionLabel?.setOnTouchListener { _, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    downX = event.rawX; downY = event.rawY; startX = params.x; startY = params.y; true
                }
                MotionEvent.ACTION_MOVE -> {
                    params.x = startX - (event.rawX - downX).toInt()
                    params.y = startY + (event.rawY - downY).toInt()
                    windowManager.updateViewLayout(container, params)
                    true
                }
                else -> false
            }
        }
        windowManager.addView(container, params)
        view = container
        return true
    }

    private fun chip(label: String, color: Int = 0xFF0F766E.toInt(), action: () -> Unit): TextView {
        val density = context.resources.displayMetrics.density
        return TextView(context).apply {
            text = label
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            setPadding((12 * density).toInt(), (8 * density).toInt(), (12 * density).toInt(), (8 * density).toInt())
            background = GradientDrawable().apply {
                setColor(color)
                cornerRadius = 14 * density
            }
            setOnClickListener { action() }
        }
    }

    private fun chipParams(density: Float) = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply {
        marginEnd = (6 * density).toInt()
    }

    fun updateQuestion(number: Int?) {
        questionLabel?.post { questionLabel?.text = if (number == null) "等待题号" else "第 $number 题" }
    }

    fun updateStatus(message: String) {
        statusLabel?.post { statusLabel?.text = message }
    }

    fun hide() {
        view?.let { runCatching { windowManager.removeView(it) } }
        view = null
        questionLabel = null
        statusLabel = null
        extra = null
        paused = false
    }
}
