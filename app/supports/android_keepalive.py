from app.supports.android_notification import postNotification

_SERVICE = "org.ghostdownloader.KeepAliveService"
_CHANNEL = "gd3_keepalive"
_NOTIF_ID = 0x47443301

class BackgroundKeepAlive:
    def __init__(self):
        self._activeReasons: set[str] = set()
        self._running = False
        self._statusMessage = ""
        self._speed = 0
        self._wakeLock = None

    def setActiveReason(self, reason: str, active: bool) -> None:
        if active:
            self._activeReasons.add(reason)
        else:
            self._activeReasons.discard(reason)
        self._updateService()

    def setWakeLock(self, active: bool) -> None:
        from jnius import autoclass, cast

        if active:
            if self._wakeLock is not None:
                return
            Context = autoclass("android.content.Context")
            PowerManager = autoclass("android.os.PowerManager")
            activity = autoclass("org.kivy.android.PythonActivity").mActivity
            powerManager = cast("android.os.PowerManager", activity.getSystemService(Context.POWER_SERVICE))
            self._wakeLock = powerManager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "GhostDownloader::Download")
            self._wakeLock.setReferenceCounted(False)
            self._wakeLock.acquire()
        elif self._wakeLock is not None:
            self._wakeLock.release()
            self._wakeLock = None

    def updateSpeed(self, speed: int) -> None:
        self._speed = speed
        if self._running:
            self._updateService()

    def _buildStatusMessage(self) -> str:
        if self._speed > 0:
            from app.supports.utils import toReadableSize

            return f"{toReadableSize(self._speed)}/s"
        if "download" in self._activeReasons:
            return "正在下载"
        return "浏览器扩展保持连接"

    def _updateService(self) -> None:
        if self._activeReasons:
            statusMessage = self._buildStatusMessage()
            if not self._running:
                self._startService(statusMessage)
                self._running = True
            elif statusMessage != self._statusMessage:
                postNotification(_CHANNEL, "后台任务", _NOTIF_ID, "Ghost Downloader", statusMessage,
                                 ongoing=True, lowImportance=True)
            self._statusMessage = statusMessage
        elif self._running:
            self._stopService()
            self._running = False
            self._statusMessage = ""

    def _startService(self, statusMessage: str) -> None:
        from jnius import autoclass

        Intent = autoclass("android.content.Intent")
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        intent = Intent(activity, autoclass(_SERVICE))
        intent.putExtra("text", statusMessage)
        if autoclass("android.os.Build$VERSION").SDK_INT >= 26:
            activity.startForegroundService(intent)
        else:
            activity.startService(intent)

    def _stopService(self) -> None:
        from jnius import autoclass

        Intent = autoclass("android.content.Intent")
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        activity.stopService(Intent(activity, autoclass(_SERVICE)))

keepAlive = BackgroundKeepAlive()

def requestIgnoreBatteryOptimizations() -> None:
    from jnius import autoclass, cast

    if autoclass("android.os.Build$VERSION").SDK_INT < 23:
        return
    Context = autoclass("android.content.Context")
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    powerManager = cast("android.os.PowerManager", activity.getSystemService(Context.POWER_SERVICE))
    if powerManager.isIgnoringBatteryOptimizations(activity.getPackageName()):
        return
    Settings = autoclass("android.provider.Settings")
    Uri = autoclass("android.net.Uri")
    Intent = autoclass("android.content.Intent")
    intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
    intent.setData(Uri.parse("package:" + activity.getPackageName()))
    activity.startActivity(intent)
