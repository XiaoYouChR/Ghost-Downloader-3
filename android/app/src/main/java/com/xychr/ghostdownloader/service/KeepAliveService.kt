package com.xychr.ghostdownloader.service

import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.xychr.ghostdownloader.MainActivity
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.engine.engineRepository
import com.xychr.ghostdownloader.ui.platform.buildLocalizedContext
import com.xychr.ghostdownloader.ui.util.formatSpeed
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable

@Serializable
data class KeepAlive(
    val reason: String = "",
    val count: Int = 0,
    val progress: Double = 0.0,
    val speed: Long = 0,
)

fun startKeepAlive(context: Context) {
    ContextCompat.startForegroundService(context, Intent(context, KeepAliveService::class.java))
}

class KeepAliveService : Service() {

    private var scope: CoroutineScope? = null

    private val openApp by lazy {
        PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java)
                .setFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
            PendingIntent.FLAG_IMMUTABLE,
        )
    }

    override fun attachBaseContext(base: Context) {
        super.attachBaseContext(buildLocalizedContext(base))
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        ServiceCompat.startForeground(
            this, NOTIF_ID_KEEP_ALIVE,
            buildNotification(KeepAlive(reason = "starting")),
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE)
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
            else 0,
        )
        if (scope?.isActive != true) {
            scope = CoroutineScope(Dispatchers.IO + Job())
            scope!!.launch { supervise() }
        }
        return START_STICKY
    }

    private suspend fun supervise() {
        val notifications = getSystemService(NotificationManager::class.java)

        engineRepository.observe<KeepAlive>("keepAlive").collect { state ->
            if (state.reason.isEmpty()) {
                stopSelf()
                return@collect
            }
            notifications.notify(NOTIF_ID_KEEP_ALIVE, buildNotification(state))
        }
    }

    private fun buildNotification(state: KeepAlive): Notification {
        val builder = NotificationCompat.Builder(this, CHANNEL_RUNNING)
            .setSmallIcon(R.drawable.ic_notification_download)
            .setContentTitle(getString(R.string.app_name))
            .setContentIntent(openApp)
            .setOngoing(true)
            .setSilent(true)

        return when (state.reason) {
            "downloading" -> builder
                .setContentText(
                    getString(
                        R.string.notification_downloading,
                        state.count, formatSpeed(state.speed),
                    )
                )
                .setStyle(
                    NotificationCompat.ProgressStyle()
                        .setProgressSegments(listOf(NotificationCompat.ProgressStyle.Segment(100)))
                        .setProgress(state.progress.toInt().coerceIn(0, 100))
                )
                .setRequestPromotedOngoing(true)
                .addAction(
                    0, getString(R.string.notification_pause_all),
                    keepAliveAction(this, isPausing = true),
                )
                .build()

            "serving" -> builder
                .setContentText(getString(R.string.notification_serving))
                .addAction(
                    0, getString(R.string.notification_resume_all),
                    keepAliveAction(this, isPausing = false),
                )
                .build()

            else -> builder
                .setContentText(getString(R.string.notification_preparing))
                .setProgress(0, 0, true)
                .build()
        }
    }

    override fun onDestroy() {
        scope?.cancel()
        scope = null
        super.onDestroy()
    }
}
