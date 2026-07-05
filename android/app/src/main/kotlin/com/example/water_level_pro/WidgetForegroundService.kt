package com.example.water_level_pro

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class WidgetForegroundService : Service() {

    companion object {
        private const val ACTION_START = "com.example.water_level_pro.action.START_WIDGET_SERVICE"
        private const val ACTION_STOP = "com.example.water_level_pro.action.STOP_WIDGET_SERVICE"
        private const val CHANNEL_ID = "widget_updates_channel"
        private const val NOTIFICATION_ID = 1107
        private const val POLL_INTERVAL_MS = 60_000L

        fun start(context: Context) {
            val intent = Intent(context, WidgetForegroundService::class.java).apply {
                action = ACTION_START
            }
            ContextCompat.startForegroundService(context, intent)
        }

        fun stop(context: Context) {
            val intent = Intent(context, WidgetForegroundService::class.java).apply {
                action = ACTION_STOP
            }
            context.startService(intent)
        }
    }

    @Volatile
    private var running = false
    private var workerThread: Thread? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }

        createNotificationChannel()
        startForeground(NOTIFICATION_ID, buildNotification())
        startWorkerIfNeeded()
        return START_STICKY
    }

    override fun onDestroy() {
        running = false
        workerThread?.interrupt()
        workerThread = null
        super.onDestroy()
    }

    private fun startWorkerIfNeeded() {
        if (running) return
        running = true

        workerThread = Thread {
            while (running) {
                try {
                    fetchAndUpdateWidget()
                } catch (_: Exception) {
                }

                try {
                    Thread.sleep(POLL_INTERVAL_MS)
                } catch (_: InterruptedException) {
                    break
                }
            }
        }.also { it.start() }
    }

    private fun fetchAndUpdateWidget() {
        val appPrefs = getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE)
        val publicKey = appPrefs.getString("flutter.widget_public_key", null)
        val deviceName = appPrefs.getString("flutter.widget_device_name", "Water Level") ?: "Water Level"

        if (publicKey.isNullOrBlank()) return

        val url = URL("https://waterlevel.pro/data-api?key=$publicKey")
        val conn = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 15_000
            readTimeout = 15_000
        }

        conn.connect()
        if (conn.responseCode != 200) {
            conn.disconnect()
            return
        }

        val body = conn.inputStream.bufferedReader().use { it.readText() }
        conn.disconnect()

        val json = JSONObject(body)

        var emptyLevel = json.optString("empty_level", "200").toDoubleOrNull() ?: 200.0
        var topMargin = json.optString("top_margin", "0").toDoubleOrNull() ?: 0.0

        if (emptyLevel == 0.0) emptyLevel = 1.0
        if (topMargin < 0.0) topMargin = 0.0

        val waterHeight = if (!json.isNull("water_height_cm")) {
            json.optString("water_height_cm", "0").toDoubleOrNull() ?: 0.0
        } else {
            val distance = json.optString("distance", "0").toDoubleOrNull() ?: 0.0
            val clamped = distance.coerceIn(topMargin, emptyLevel)
            (emptyLevel - clamped).coerceAtLeast(0.0)
        }

        var usable = emptyLevel - topMargin
        if (usable <= 0.0) usable = 1.0
        val fillPct = (waterHeight / usable).coerceIn(0.0, 1.0)

        val liters = if (!json.isNull("current_liters")) {
            val l = json.optString("current_liters", "0").toDoubleOrNull() ?: 0.0
            "${l.toInt()} L"
        } else {
            ""
        }

        val widgetPrefs = getSharedPreferences("HomeWidgetPreferences", Context.MODE_PRIVATE)
        widgetPrefs.edit()
            .putString("deviceName", deviceName)
            .putString("percent", "${(fillPct * 100).toInt()}%")
            .putString("level", "${String.format("%.1f", waterHeight)} cm")
            .putString("liters", liters)
            .apply()

        val manager = AppWidgetManager.getInstance(this)
        val ids = manager.getAppWidgetIds(ComponentName(this, WaterLevelWidgetProvider::class.java))
        if (ids.isNotEmpty()) {
            val intent = Intent(this, WaterLevelWidgetProvider::class.java).apply {
                action = AppWidgetManager.ACTION_APPWIDGET_UPDATE
                putExtra(AppWidgetManager.EXTRA_APPWIDGET_IDS, ids)
            }
            sendBroadcast(intent)
        }
    }

    private fun buildNotification(): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle("WaterLevel widget")
            .setContentText("Actualizando cada 1 minuto")
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return

        val manager = getSystemService(NotificationManager::class.java)
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Widget Updates",
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "Background updates for WaterLevel widget"
        }
        manager.createNotificationChannel(channel)
    }
}