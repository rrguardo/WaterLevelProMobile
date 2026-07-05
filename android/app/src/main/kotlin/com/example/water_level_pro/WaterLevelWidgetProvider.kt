package com.example.water_level_pro

import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.content.SharedPreferences
import android.view.View
import android.widget.RemoteViews

class WaterLevelWidgetProvider : AppWidgetProvider() {

    override fun onEnabled(context: Context) {
        super.onEnabled(context)
        WidgetForegroundService.start(context)
    }

    override fun onDisabled(context: Context) {
        super.onDisabled(context)
        WidgetForegroundService.stop(context)
    }

    override fun onUpdate(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetIds: IntArray
    ) {
        WidgetForegroundService.start(context)
        val prefs: SharedPreferences =
            context.getSharedPreferences("HomeWidgetPreferences", Context.MODE_PRIVATE)

        val settings: SharedPreferences =
            context.getSharedPreferences("WidgetSettings", Context.MODE_PRIVATE)

        val percentStr = prefs.getString("percent", "--%") ?: "--%"
        val level = prefs.getString("level", "-- cm") ?: "-- cm"
        val deviceName = prefs.getString("deviceName", "Water Level") ?: "Water Level"

        val showSubtext = settings.getBoolean("show_subtext", false)
        val subtextMode = settings.getString("subtext_mode", "cm") ?: "cm"

        val fillLevel = parseFillLevel(percentStr)

        for (appWidgetId in appWidgetIds) {
            val views = RemoteViews(context.packageName, R.layout.waterlevel_widget_layout)
            views.setTextViewText(R.id.widget_percent, percentStr)
            views.setInt(R.id.water_fill_view, "setImageLevel", fillLevel)

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

            appWidgetManager.updateAppWidget(appWidgetId, views)
        }
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
