"""Android 本地通知 —— NotificationManager 投递, 完成 toast 与常驻通知共用 postNotification。须主线程调。"""

_CHANNEL = "gd3_downloads"


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
        flags |= PendingIntent.FLAG_IMMUTABLE  # 31+ 必须显式可变性
    return PendingIntent.getActivity(activity, 0, intent, flags)


def postNotification(channelId: str, channelName: str, notifId: int, title: str, text: str,
                     *, ongoing: bool, lowImportance: bool) -> None:
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
    builder.setSmallIcon(activity.getApplicationInfo().icon)  # 必填, 缺则不弹
    builder.setContentTitle(title)
    builder.setContentText(text)
    builder.setOngoing(ongoing)
    builder.setAutoCancel(not ongoing)
    builder.setOnlyAlertOnce(True)  # 每秒刷, 只首次提醒
    builder.setContentIntent(_reopenAppIntent(activity))
    manager.notify(notifId, builder.build())  # 同 notifId 再投即更新


def notifyDownloadComplete(notifyKey: str, title: str, text: str) -> None:
    postNotification(_CHANNEL, "下载", hash(notifyKey) & 0x7FFFFFFF, title, text,
                     ongoing=False, lowImportance=False)


def requestNotificationPermission() -> None:
    from jnius import autoclass

    if autoclass("android.os.Build$VERSION").SDK_INT < 33:  # POST_NOTIFICATIONS 仅 13+ 需运行时授权
        return
    PackageManager = autoclass("android.content.pm.PackageManager")
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    permission = "android.permission.POST_NOTIFICATIONS"
    if activity.checkSelfPermission(permission) != PackageManager.PERMISSION_GRANTED:
        activity.requestPermissions([permission], 0)
