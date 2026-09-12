package com.xychr.ghostdownloader.service

import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import com.xychr.ghostdownloader.*
import com.xychr.ghostdownloader.engine.EngineRepository
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.Serializable

const val CHANNEL_PAIR = "pair"
const val NOTIF_ID_PAIR = 2

private const val ACTION_APPROVE = "com.xychr.ghostdownloader.PAIR_APPROVE"
private const val ACTION_REJECT = "com.xychr.ghostdownloader.PAIR_REJECT"
private const val EXTRA_REQUEST_ID = "requestId"

@Serializable
data class PairRequest(
    val requestId: String = "",
    val clientKind: String = "",
    val extensionVersion: String = "",
)

fun buildPairNotification(context: Context, pair: PairRequest): Notification =
    NotificationCompat.Builder(context, CHANNEL_PAIR)
        .setSmallIcon(R.drawable.ic_notification_download)
        .setContentTitle(context.getString(R.string.pair_title))
        .setContentText(
            context.getString(
                R.string.pair_message,
                pair.clientKind.ifEmpty { context.getString(R.string.pair_unknown_client) },
                pair.extensionVersion,
            )
        )
        .setCategory(NotificationCompat.CATEGORY_RECOMMENDATION)
        .setAutoCancel(true)
        .setOnlyAlertOnce(true)
        .addAction(
            0, context.getString(R.string.pair_approve),
            buildPairIntent(context, ACTION_APPROVE, pair.requestId),
        )
        .addAction(
            0, context.getString(R.string.pair_reject),
            buildPairIntent(context, ACTION_REJECT, pair.requestId),
        )
        .build()

private fun buildPairIntent(context: Context, action: String, requestId: String) =
    PendingIntent.getBroadcast(
        context,
        action.hashCode(),
        Intent(context, BrowserPairingReceiver::class.java)
            .setAction(action)
            .putExtra(EXTRA_REQUEST_ID, requestId),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )

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
