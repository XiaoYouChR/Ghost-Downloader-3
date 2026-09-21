package com.xychr.ghostdownloader.service

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationManagerCompat
import com.xychr.ghostdownloader.engine.engineRepository
import kotlinx.coroutines.runBlocking

private const val ACTION_RETRY = "com.xychr.ghostdownloader.RETRY_TASK"
private const val EXTRA_TASK_ID = "taskId"

fun retryAction(context: Context, taskId: String): PendingIntent =
    PendingIntent.getBroadcast(
        context, taskId.hashCode(),
        Intent(context, TaskNoticeActionReceiver::class.java)
            .setAction(ACTION_RETRY)
            .putExtra(EXTRA_TASK_ID, taskId),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )

class TaskNoticeActionReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val taskId = intent.getStringExtra(EXTRA_TASK_ID) ?: return
        if (intent.action != ACTION_RETRY) return
        val pending = goAsync()
        Thread {
            runBlocking { engineRepository.invoke("redownload", taskId) }
            NotificationManagerCompat.from(context).cancel(taskNoticeId(taskId))
            pending.finish()
        }.start()
    }
}
