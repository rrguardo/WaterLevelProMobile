package com.example.water_level_pro

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Build
import android.view.View
import android.widget.RemoteViews

class WaterLevelWidgetProvider : AppWidgetProvider() {

    override fun onUpdate(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetIds: IntArray
    ) {
        val prefs = context.getSharedPreferences("HomeWidgetPreferences", Context.MODE_PRIVATE)

        val percentStr = prefs.getString("percent", "--%") ?: "--%"
        val level = prefs.getString("level", "-- cm") ?: "-- cm"
        val deviceName = prefs.getString("deviceName", "Water Level") ?: "Water Level"
        val voltage = prefs.getString("voltage", "") ?: ""
        val isOnline = prefs.getString("isOnline", "true") == "true"
        val showSubtext = prefs.getString("show_subtext", "false") == "true"
        val subtextMode = prefs.getString("subtext_mode", "cm") ?: "cm"
        val showCornerTl = prefs.getString("show_corner_online", "true") != "false"
        val showCornerTr = prefs.getString("show_corner_voltage", "true") != "false"
        val showCornerBl = prefs.getString("show_corner_level", "true") != "false"

        val fillLevel = parseFillLevel(percentStr)
        val density = context.resources.displayMetrics.density

        val brandingIntent = Intent(Intent.ACTION_VIEW, Uri.parse("https://waterlevel.pro"))
        val brandingFlags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        } else {
            PendingIntent.FLAG_UPDATE_CURRENT
        }
        val brandingPendingIntent = PendingIntent.getActivity(
            context, 0, brandingIntent, brandingFlags
        )

        for (appWidgetId in appWidgetIds) {
            updateWidget(
                context,
                appWidgetManager,
                appWidgetId,
                percentStr,
                level,
                deviceName,
                voltage,
                isOnline,
                showSubtext,
                subtextMode,
                showCornerTl,
                showCornerTr,
                showCornerBl,
                fillLevel,
                density,
                brandingPendingIntent
            )
        }
    }

    override fun onAppWidgetOptionsChanged(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetId: Int,
        newOptions: Bundle
    ) {
        onUpdate(context, appWidgetManager, intArrayOf(appWidgetId))
    }

    private fun updateWidget(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetId: Int,
        percentStr: String,
        level: String,
        deviceName: String,
        voltage: String,
        isOnline: Boolean,
        showSubtext: Boolean,
        subtextMode: String,
        showCornerTl: Boolean,
        showCornerTr: Boolean,
        showCornerBl: Boolean,
        fillLevel: Int,
        density: Float,
        brandingPendingIntent: PendingIntent
    ) {
        val views = RemoteViews(context.packageName, R.layout.waterlevel_widget_layout)
        views.setTextViewText(R.id.widget_percent, percentStr)
        views.setInt(R.id.water_fill_view, "setImageLevel", fillLevel)

        // Subtext below percentage
        if (showSubtext) {
            val subtext = when (subtextMode) {
                "name" -> deviceName
                "both" -> "$deviceName • $level"
                else -> level
            }
            views.setTextViewText(R.id.widget_subtext, subtext)
            views.setViewVisibility(R.id.widget_subtext, View.VISIBLE)
        } else {
            views.setViewVisibility(R.id.widget_subtext, View.GONE)
        }

        // Top-left: Online/offline indicator
        if (isOnline) {
            views.setViewVisibility(R.id.icon_online, View.VISIBLE)
            views.setViewVisibility(R.id.icon_offline, View.GONE)
            views.setTextColor(R.id.text_online, 0xFF4CAF50.toInt())
            views.setTextViewText(R.id.text_online, "Online")
        } else {
            views.setViewVisibility(R.id.icon_online, View.GONE)
            views.setViewVisibility(R.id.icon_offline, View.VISIBLE)
            views.setTextColor(R.id.text_online, 0xFFEF5350.toInt())
            views.setTextViewText(R.id.text_online, "Offline")
        }

        // Top-right: Voltage
        views.setTextViewText(R.id.text_voltage, voltage.ifEmpty { "--" })

        // Bottom-left: Water level (cm)
        views.setTextViewText(R.id.text_level, level)

        // Corner visibility
        views.setViewVisibility(R.id.corner_tl, if (showCornerTl) View.VISIBLE else View.GONE)
        views.setViewVisibility(R.id.corner_tr, if (showCornerTr) View.VISIBLE else View.GONE)
        views.setViewVisibility(R.id.corner_bl, if (showCornerBl) View.VISIBLE else View.GONE)

        // Branding link
        views.setOnClickPendingIntent(R.id.widget_branding, brandingPendingIntent)

        // Sphere size: ~70% of widget, 1:1
        try {
            val options = appWidgetManager.getAppWidgetOptions(appWidgetId)
            val minWdp = options.getInt(AppWidgetManager.OPTION_APPWIDGET_MIN_WIDTH, 120)
            val minHdp = options.getInt(AppWidgetManager.OPTION_APPWIDGET_MIN_HEIGHT, 120)
            val maxWdp = options.getInt(AppWidgetManager.OPTION_APPWIDGET_MAX_WIDTH, minWdp)
            val maxHdp = options.getInt(AppWidgetManager.OPTION_APPWIDGET_MAX_HEIGHT, minHdp)

            val widgetWdp = maxOf(minWdp, maxWdp)
            val widgetHdp = maxOf(minHdp, maxHdp)
            val targetByHeightDp = (widgetHdp * 0.7f).toInt()
            val sphereSizeDp = minOf(targetByHeightDp, widgetWdp).coerceAtLeast(48)
            val sphereSizePx = (sphereSizeDp * density).toInt()

            views.setInt(R.id.sphere_frame, "setMinimumWidth", sphereSizePx)
            views.setInt(R.id.sphere_frame, "setMinimumHeight", sphereSizePx)
            views.setInt(R.id.sphere_inner, "setMinimumWidth", sphereSizePx)
            views.setInt(R.id.sphere_inner, "setMinimumHeight", sphereSizePx)
            for (id in intArrayOf(
                R.id.sphere_glow, R.id.sphere_bg,
                R.id.water_fill_view, R.id.sphere_highlight
            )) {
                views.setInt(id, "setMinimumWidth", sphereSizePx)
                views.setInt(id, "setMinimumHeight", sphereSizePx)
            }
        } catch (_: Exception) {
            // Fallback
        }

        appWidgetManager.updateAppWidget(appWidgetId, views)
    }

    private fun parseFillLevel(percent: String): Int {
        return try {
            val num = percent.replace("%", "").replace(",", ".").trim().toFloat()
            (num * 100).toInt().coerceIn(0, 10000)
        } catch (_: NumberFormatException) {
            0
        }
    }
}
