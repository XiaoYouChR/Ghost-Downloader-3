from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication

if TYPE_CHECKING:
    from app.models.task import Task

DOWNLOAD_CHANNEL = "gd3_downloads"


def notify(channelId: str, channelName: str, notificationId: int,
           title: str, text: str, *, ongoing: bool, lowImportance: bool) -> None:
    from jnius import autoclass, cast

    Context = autoclass("android.content.Context")
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    manager = cast("android.app.NotificationManager", activity.getSystemService(Context.NOTIFICATION_SERVICE))

    if autoclass("android.os.Build$VERSION").SDK_INT >= 26:
        NotificationManager = autoclass("android.app.NotificationManager")
        NotificationChannel = autoclass("android.app.NotificationChannel")
        importance = NotificationManager.IMPORTANCE_LOW if lowImportance else NotificationManager.IMPORTANCE_DEFAULT
        manager.createNotificationChannel(NotificationChannel(channelId, channelName, importance))
        builder = autoclass("android.app.Notification$Builder")(activity, channelId)
    else:
        builder = autoclass("android.app.Notification$Builder")(activity)

    builder.setSmallIcon(activity.getApplicationInfo().icon)
    builder.setContentTitle(title)
    builder.setContentText(text)
    builder.setOngoing(ongoing)
    builder.setAutoCancel(not ongoing)
    builder.setOnlyAlertOnce(True)
    builder.setContentIntent(_reopenAppIntent(activity))
    manager.notify(notificationId, builder.build())


def notifyTaskCompleted(task: Task) -> None:
    notify(DOWNLOAD_CHANNEL, QCoreApplication.translate("Notifications", "下载"),
           hash(task.taskId) & 0x7FFFFFFF,
           QCoreApplication.translate("Notifications", "下载完成"), task.name,
           ongoing=False, lowImportance=False)


DISK_SPACE_NOTIFICATION_ID = 0x6764_0003


def notifyDiskSpaceInsufficient(free: int, needed: int) -> None:
    from app.format import toReadableSize
    notify(DOWNLOAD_CHANNEL, QCoreApplication.translate("Notifications", "下载"),
           DISK_SPACE_NOTIFICATION_ID,
           QCoreApplication.translate("Notifications", "磁盘空间不足"),
           QCoreApplication.translate("Notifications", "剩余 {0}，需要 {1}，任务未自动开始").format(
               toReadableSize(free), toReadableSize(needed)),
           ongoing=False, lowImportance=False)


BROWSER_PUSH_NOTIFICATION_ID = 0x6764_0001
BROWSER_PAIR_NOTIFICATION_ID = 0x6764_0002


def notifyBrowserTaskAdded(tasks: list[Task]) -> None:
    if not tasks:
        return
    count = len(tasks)
    title = QCoreApplication.translate("Notifications", "浏览器推送") if count == 1 \
        else QCoreApplication.translate("Notifications", "浏览器推送（{count}）").format(count=count)
    text = tasks[0].name if count == 1 else "、".join(t.name for t in tasks[:3])
    if count > 3:
        text += QCoreApplication.translate("Notifications", "等 {count} 个").format(count=count)
    notify(DOWNLOAD_CHANNEL, QCoreApplication.translate("Notifications", "下载"),
           BROWSER_PUSH_NOTIFICATION_ID,
           title, text, ongoing=False, lowImportance=False)


def notifyBrowserPaired(peerAddress: str) -> None:
    notify(DOWNLOAD_CHANNEL, QCoreApplication.translate("Notifications", "下载"),
           BROWSER_PAIR_NOTIFICATION_ID,
           QCoreApplication.translate("Notifications", "浏览器扩展已连接"), peerAddress,
           ongoing=False, lowImportance=True)


def isNotificationEnabled() -> bool:
    from jnius import autoclass, cast

    Context = autoclass("android.content.Context")
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    manager = cast("android.app.NotificationManager",
                    activity.getSystemService(Context.NOTIFICATION_SERVICE))
    return manager.areNotificationsEnabled()


def requestNotificationPermission() -> None:
    from jnius import autoclass

    if isNotificationEnabled():
        return
    Settings = autoclass("android.provider.Settings")
    Intent = autoclass("android.content.Intent")
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    intent = Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
    intent.putExtra(Settings.EXTRA_APP_PACKAGE, activity.getPackageName())
    activity.startActivity(intent)


def _reopenAppIntent(activity):
    from jnius import autoclass

    Intent = autoclass("android.content.Intent")
    PendingIntent = autoclass("android.app.PendingIntent")
    PythonActivity = autoclass("org.kivy.android.PythonActivity")

    intent = Intent(activity, PythonActivity)
    intent.setAction(Intent.ACTION_MAIN)
    intent.addCategory(Intent.CATEGORY_LAUNCHER)
    intent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)
    flags = PendingIntent.FLAG_UPDATE_CURRENT
    if autoclass("android.os.Build$VERSION").SDK_INT >= 23:
        flags |= PendingIntent.FLAG_IMMUTABLE
    return PendingIntent.getActivity(activity, 0, intent, flags)
