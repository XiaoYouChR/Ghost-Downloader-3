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
        flags |= PendingIntent.FLAG_IMMUTABLE
    return PendingIntent.getActivity(activity, 0, intent, flags)

def postNotification(channelId: str, channelName: str, notificationId: int, title: str, text: str,
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
    builder.setSmallIcon(activity.getApplicationInfo().icon)
    builder.setContentTitle(title)
    builder.setContentText(text)
    builder.setOngoing(ongoing)
    builder.setAutoCancel(not ongoing)
    builder.setOnlyAlertOnce(True)
    builder.setContentIntent(_reopenAppIntent(activity))
    manager.notify(notificationId, builder.build())

def notifyDownloadComplete(taskId: str, title: str, message: str) -> None:
    postNotification(_CHANNEL, "下载", hash(taskId) & 0x7FFFFFFF, title, message,
                     ongoing=False, lowImportance=False)

def requestNotificationPermission() -> None:
    from jnius import autoclass

    if autoclass("android.os.Build$VERSION").SDK_INT < 33:
        return
    PackageManager = autoclass("android.content.pm.PackageManager")
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    permission = "android.permission.POST_NOTIFICATIONS"
    if activity.checkSelfPermission(permission) != PackageManager.PERMISSION_GRANTED:
        activity.requestPermissions([permission], 0)
