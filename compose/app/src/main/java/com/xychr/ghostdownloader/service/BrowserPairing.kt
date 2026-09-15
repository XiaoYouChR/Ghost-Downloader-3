package com.xychr.ghostdownloader.service

import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.xychr.ghostdownloader.engine.EngineRepository
import kotlinx.coroutines.runBlocking

private const val ACTION_APPROVE = "com.xychr.ghostdownloader.PAIR_APPROVE"
private const val ACTION_REJECT = "com.xychr.ghostdownloader.PAIR_REJECT"
private const val EXTRA_REQUEST_ID = "requestId"

fun pairAction(context: Context, isApproved: Boolean, requestId: String): PendingIntent {
    val action = if (isApproved) ACTION_APPROVE else ACTION_REJECT
    return PendingIntent.getBroadcast(
        context,
        action.hashCode(),
        Intent(context, BrowserPairingReceiver::class.java)
            .setAction(action)
            .putExtra(EXTRA_REQUEST_ID, requestId),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )
}

class BrowserPairingReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val requestId = intent.getStringExtra(EXTRA_REQUEST_ID) ?: return
        val isApproved = when (intent.action) {
            ACTION_APPROVE -> true
            ACTION_REJECT -> false
            else -> return
        }
        val pending = goAsync()
        Thread {
            runBlocking { EngineRepository.invoke("setBrowserPairApproval", requestId, isApproved) }
            context.getSystemService(NotificationManager::class.java).cancel(NOTIF_ID_PAIR)
            pending.finish()
        }.start()
    }
}
