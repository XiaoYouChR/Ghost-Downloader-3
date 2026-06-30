from __future__ import annotations

from typing import TYPE_CHECKING

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
    notify(DOWNLOAD_CHANNEL, "下载", hash(task.taskId) & 0x7FFFFFFF,
           "下载完成", task.name, ongoing=False, lowImportance=False)


BROWSER_PUSH_NOTIFICATION_ID = 0x6764_0001
BROWSER_PAIR_NOTIFICATION_ID = 0x6764_0002


def notifyBrowserTaskAdded(tasks: list[Task]) -> None:
    if not tasks:
        return
    count = len(tasks)
    title = "浏览器推送" if count == 1 else f"浏览器推送 ({count})"
    text = tasks[0].name if count == 1 else "、".join(t.name for t in tasks[:3])
    if count > 3:
        text += f" 等 {count} 项"
    notify(DOWNLOAD_CHANNEL, "下载", BROWSER_PUSH_NOTIFICATION_ID,
           title, text, ongoing=False, lowImportance=False)


def notifyBrowserPaired(peerAddress: str) -> None:
    notify(DOWNLOAD_CHANNEL, "下载", BROWSER_PAIR_NOTIFICATION_ID,
           "浏览器扩展已连接", peerAddress, ongoing=False, lowImportance=True)


def requestNotificationPermission() -> None:
    from jnius import autoclass

    if autoclass("android.os.Build$VERSION").SDK_INT < 33:
        return
    PackageManager = autoclass("android.content.pm.PackageManager")
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    permission = "android.permission.POST_NOTIFICATIONS"
    if activity.checkSelfPermission(permission) != PackageManager.PERMISSION_GRANTED:
        activity.requestPermissions([permission], 0)


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
