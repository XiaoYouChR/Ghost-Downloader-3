package com.xychr.ghostdownloader.service

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.xychr.ghostdownloader.engine.EngineRepository
import kotlinx.coroutines.runBlocking

private const val ACTION_PAUSE_ALL = "com.xychr.ghostdownloader.PAUSE_ALL"
private const val ACTION_RESUME_ALL = "com.xychr.ghostdownloader.RESUME_ALL"

fun keepAliveAction(context: Context, isPausing: Boolean): PendingIntent {
    val action = if (isPausing) ACTION_PAUSE_ALL else ACTION_RESUME_ALL
    return PendingIntent.getBroadcast(
        context, action.hashCode(),
        Intent(context, KeepAliveActionReceiver::class.java).setAction(action),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )
}

class KeepAliveActionReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val name = when (intent.action) {
            ACTION_PAUSE_ALL -> "pauseAll"
            ACTION_RESUME_ALL -> "resumeAll"
            else -> return
        }
        val pending = goAsync()
        Thread {
            runBlocking { EngineRepository.invoke(name) }
            pending.finish()
        }.start()
    }
}
