package com.local.fenbistudy.capture

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.provider.Settings
import android.util.TypedValue
import android.view.Gravity
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.TextView

/** Stays on top of Xiaomi settings so the user only has to hit the system switch. */
object PermissionCoachOverlay {
    private var view: LinearLayout? = null

    fun show(context: Context, message: String = "打开「${VendorGuide.SERVICE_LABEL}」这一个开关，然后按返回") {
        if (!Settings.canDrawOverlays(context) || view != null) return
        val app = context.applicationContext
        val windowManager = app.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val density = app.resources.displayMetrics.density
        val card = LinearLayout(app).apply {
            orientation = LinearLayout.VERTICAL
            val pad = (14 * density).toInt()
            setPadding(pad, pad, pad, pad)
            background = GradientDrawable().apply {
                setColor(0xF2115E59.toInt())
                cornerRadius = 18 * density
            }
        }
        TextView(app).apply {
            text = "只差最后一步"
            setTextColor(Color.WHITE)
            setTypeface(typeface, Typeface.BOLD)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
        }.also(card::addView)
        TextView(app).apply {
            text = message
            setTextColor(0xFFE7F8F5.toInt())
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            setPadding(0, (6 * density).toInt(), 0, 0)
        }.also(card::addView)
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            android.graphics.PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.CENTER_HORIZONTAL
            y = (24 * density).toInt()
        }
        runCatching { windowManager.addView(card, params) }
            .onSuccess { view = card }
    }

    fun hide(context: Context) {
        val current = view ?: return
        val windowManager = context.applicationContext.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        runCatching { windowManager.removeView(current) }
        view = null
    }
}
