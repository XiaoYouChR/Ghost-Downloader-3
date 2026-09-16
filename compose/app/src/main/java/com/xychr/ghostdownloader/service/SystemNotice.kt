package com.xychr.ghostdownloader.service

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.xychr.ghostdownloader.ui.navigation.DESTINATION_DRAFT
import com.xychr.ghostdownloader.ui.navigation.EXTRA_DESTINATION
import com.xychr.ghostdownloader.MainActivity
import com.xychr.ghostdownloader.ui.navigation.toDestination
import com.xychr.ghostdownloader.R
import com.xychr.ghostdownloader.i18n.engineText
import com.xychr.ghostdownloader.model.Notice
import com.xychr.ghostdownloader.model.PairRequest
import com.xychr.ghostdownloader.ui.components.category.categoryIconRes
import com.xychr.ghostdownloader.ui.platform.folderIntent
import com.xychr.ghostdownloader.ui.platform.taskFileIntent
import com.xychr.ghostdownloader.ui.util.formatSize

const val CHANNEL_RUNNING = "running"
const val CHANNEL_DONE = "done"
const val CHANNEL_PROBLEM = "problem"

/** 渠道 id 已经落在用户设备上，换 id 会孤立用户已经调过的渠道偏好，所以只换显示名。 */
const val CHANNEL_CONFIRM = "pair"

const val NOTIF_ID_KEEP_ALIVE = 1
const val NOTIF_ID_PAIR = 2
const val NOTIF_ID_DRAFT = 3
const val NOTIF_ID_DISK = 4
const val NOTIF_ID_DONE_SUMMARY = 5

private const val GROUP_DONE = "done"

/** 固定 id 占低位，任务级 id 从 taskId 派生并抬到高位段，两者不会撞车。 */
private fun taskNoticeId(taskId: String) = (taskId.hashCode() and 0x7FFFFFFF) or 0x40000000

fun Context.createNoticeChannels() {
    getSystemService(NotificationManager::class.java).apply {
        createNotificationChannel(channel(CHANNEL_RUNNING, R.string.notification_channel_running, NotificationManager.IMPORTANCE_LOW))
        createNotificationChannel(channel(CHANNEL_DONE, R.string.notification_channel_done, NotificationManager.IMPORTANCE_DEFAULT))
        createNotificationChannel(channel(CHANNEL_PROBLEM, R.string.notification_channel_problem, NotificationManager.IMPORTANCE_HIGH))
        createNotificationChannel(channel(CHANNEL_CONFIRM, R.string.notification_channel_confirm, NotificationManager.IMPORTANCE_HIGH))
    }
}

private fun Context.channel(id: String, name: Int, importance: Int) =
    NotificationChannel(id, getString(name), importance)

/**
 * areNotificationsEnabled 在 33+ 上就包含了运行时权限被拒的情况，比 checkSelfPermission 更准——
 * 后者对 33 以下不存在的 POST_NOTIFICATIONS 会一律返回 DENIED，反而把老系统的通知也掐了。
 */
@SuppressLint("MissingPermission")
fun Context.send(notice: Notice) {
    val notifications = NotificationManagerCompat.from(this)
    if (!notifications.areNotificationsEnabled()) return
    when (notice) {
        is Notice.TaskCompleted -> {
            notifications.notify(taskNoticeId(notice.taskId), buildCompleted(notice))
            notifications.notify(NOTIF_ID_DONE_SUMMARY, buildDoneSummary())
        }
        is Notice.TaskFailed -> notifications.notify(taskNoticeId(notice.taskId), buildFailed(notice))
        is Notice.DiskSpace -> notifications.notify(NOTIF_ID_DISK, buildDiskSpace(notice))
        is Notice.DraftTaken -> notifications.notify(NOTIF_ID_DRAFT, buildDraftTaken(notice))
        // 纯 FYI，后台不值得打扰。Notices 已经拦掉，这里只是把穷尽性补全。
        is Notice.ExtensionUpdated -> Unit
    }
}

@SuppressLint("MissingPermission")
fun Context.sendPair(pair: PairRequest?) {
    val notifications = NotificationManagerCompat.from(this)
    if (pair == null) {
        notifications.cancel(NOTIF_ID_PAIR)
        return
    }
    if (notifications.areNotificationsEnabled()) notifications.notify(NOTIF_ID_PAIR, buildPair(pair))
}

private fun Context.buildCompleted(notice: Notice.TaskCompleted): Notification {
    val file = taskFileIntent(notice.path)
    return base(CHANNEL_DONE)
        .setContentTitle(getString(R.string.notice_completed))
        .setContentText(notice.name)
        .setSmallIcon(categoryIconRes(notice.icon))
        .setContentIntent(file?.let(::activity) ?: openApp())
        .apply {
            file?.let { addAction(0, getString(R.string.notice_open_file), activity(it)) }
        }
        .addAction(0, getString(R.string.notice_open_folder), activity(folderIntent(notice.folder)))
        .setAutoCancel(true)
        .setGroup(GROUP_DONE)
        .build()
}

/** 多任务同时完成时，Android 要求组里有一条 summary，否则分组不生效。 */
private fun Context.buildDoneSummary(): Notification =
    base(CHANNEL_DONE)
        .setContentTitle(getString(R.string.notice_completed))
        .setContentIntent(openApp())
        .setAutoCancel(true)
        .setGroup(GROUP_DONE)
        .setGroupSummary(true)
        .build()

private fun Context.buildFailed(notice: Notice.TaskFailed): Notification {
    val reason = engineText(notice.message, notice.params)
    return base(CHANNEL_PROBLEM)
        .setContentTitle(getString(R.string.notice_failed, notice.name))
        .setContentText(reason)
        .setStyle(NotificationCompat.BigTextStyle().bigText(reason))
        .setContentIntent(openApp(toDestination(notice.taskId)))
        .setAutoCancel(true)
        .build()
}

private fun Context.buildDiskSpace(notice: Notice.DiskSpace): Notification =
    base(CHANNEL_PROBLEM)
        .setContentTitle(getString(R.string.notice_disk_space))
        .setContentText(
            getString(R.string.notice_disk_space_desc, formatSize(notice.free), formatSize(notice.needed))
        )
        .setContentIntent(openApp())
        .setAutoCancel(true)
        .build()

private fun Context.buildDraftTaken(notice: Notice.DraftTaken): Notification =
    base(CHANNEL_CONFIRM)
        .setContentTitle(getString(R.string.notice_draft_taken))
        .setContentText(resources.getQuantityString(R.plurals.notice_draft_taken_desc, notice.count, notice.count))
        .setContentIntent(openApp(DESTINATION_DRAFT))
        .setAutoCancel(true)
        .build()

private fun Context.buildPair(pair: PairRequest): Notification =
    base(CHANNEL_CONFIRM)
        .setContentTitle(getString(R.string.pair_title))
        .setContentText(
            getString(
                R.string.pair_message,
                pair.clientKind.ifEmpty { getString(R.string.pair_unknown_client) },
                pair.extensionVersion,
                pair.peerAddress,
            )
        )
        .setCategory(NotificationCompat.CATEGORY_RECOMMENDATION)
        .setOnlyAlertOnce(true)
        .setAutoCancel(true)
        .addAction(0, getString(R.string.pair_approve), pairAction(this, true, pair.requestId))
        .addAction(0, getString(R.string.pair_reject), pairAction(this, false, pair.requestId))
        .build()

private fun Context.base(channelId: String) =
    NotificationCompat.Builder(this, channelId)
        .setSmallIcon(R.drawable.ic_notification_download)

private fun Context.activity(intent: Intent) = PendingIntent.getActivity(
    this, intent.filterHashCode(), intent,
    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
)

private fun Context.openApp(destination: String? = null) = PendingIntent.getActivity(
    this, destination.hashCode(),
    Intent(this, MainActivity::class.java)
        .setFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        .apply { destination?.let { putExtra(EXTRA_DESTINATION, it) } },
    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
)
