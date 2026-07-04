from PySide6.QtCore import QCoreApplication

from app.platform.android_notification import notify

REASON_DOWNLOAD = "download"
REASON_BROWSER = "browser"

SERVICE_CLASS = "org.ghostdownloader.KeepAliveService"
KEEPALIVE_CHANNEL = "gd3_keepalive"
KEEPALIVE_NOTIF_ID = 0x47443301


class BackgroundKeepAlive:
    def __init__(self):
        self._activeReasons: set[str] = set()
        self._running = False
        self._statusMessage = ""
        self._speed = 0
        self._wakeLock = None

    def holdFor(self, reason: str) -> None:
        self._activeReasons.add(reason)
        if reason == REASON_DOWNLOAD:
            self._setWakeLock(True)
        self._updateService()

    def release(self, reason: str) -> None:
        self._activeReasons.discard(reason)
        if reason == REASON_DOWNLOAD:
            self._setWakeLock(False)
        self._updateService()

    def setSpeed(self, speed: int) -> None:
        self._speed = speed
        if self._running:
            self._updateService()

    def _setWakeLock(self, active: bool) -> None:
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

    def _updateService(self) -> None:
        if self._activeReasons:
            statusMessage = self._buildStatusMessage()
            if not self._running:
                self._startService(statusMessage)
                self._running = True
            elif statusMessage != self._statusMessage:
                notify(KEEPALIVE_CHANNEL, QCoreApplication.translate("KeepAlive", "后台任务"),
                       KEEPALIVE_NOTIF_ID, "Ghost Downloader", statusMessage,
                       ongoing=True, lowImportance=True)
            self._statusMessage = statusMessage
        elif self._running:
            self._stopService()
            self._running = False
            self._statusMessage = ""

    def _buildStatusMessage(self) -> str:
        if self._speed > 0:
            from app.format import toReadableSize
            return f"{toReadableSize(self._speed)}/s"
        if REASON_DOWNLOAD in self._activeReasons:
            return QCoreApplication.translate("KeepAlive", "下载中")
        return QCoreApplication.translate("KeepAlive", "浏览器扩展已连接")

    def _startService(self, statusMessage: str) -> None:
        from jnius import autoclass
        Intent = autoclass("android.content.Intent")
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        intent = Intent(activity, autoclass(SERVICE_CLASS))
        intent.putExtra("text", statusMessage)
        if autoclass("android.os.Build$VERSION").SDK_INT >= 26:
            activity.startForegroundService(intent)
        else:
            activity.startService(intent)

    def _stopService(self) -> None:
        from jnius import autoclass
        Intent = autoclass("android.content.Intent")
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        activity.stopService(Intent(activity, autoclass(SERVICE_CLASS)))


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
