"""Android 后台保活 —— 同进程前台服务把宿主进程钉在前台优先级, 切后台不被回收。须主线程调。"""

from app.supports.android_notification import postNotification

_SERVICE = "org.ghostdownloader.KeepAliveService"
_CHANNEL = "gd3_keepalive"  # 须与 KeepAliveService.java 一致
_NOTIF_ID = 0x47443301  # 须与 KeepAliveService.java 一致


class AndroidKeepAlive:
    """按理由引用计数: 任一理由("download"/"browser")在即起前台服务, 全清才停。"""

    def __init__(self):
        self._reasons: set[str] = set()
        self._running = False
        self._text = ""
        self._speed = 0
        self._wakeLock = None

    def setReason(self, reason: str, active: bool) -> None:
        if active:
            self._reasons.add(reason)
        else:
            self._reasons.discard(reason)
        self._apply()

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
            self._apply()

    def _statusText(self) -> str:
        if self._speed > 0:
            from app.supports.utils import toReadableSize

            return f"{toReadableSize(self._speed)}/s"
        if "download" in self._reasons:
            return "正在下载"
        return "浏览器扩展保持连接"

    def _apply(self) -> None:
        if self._reasons:
            text = self._statusText()
            if not self._running:
                self._start(text)
                self._running = True
            elif text != self._text:  # notify 同 id 更新, 不重发服务(避 12+ 后台起 FGS 限制)
                postNotification(_CHANNEL, "后台任务", _NOTIF_ID, "Ghost Downloader", text,
                                 ongoing=True, lowImportance=True)
            self._text = text
        elif self._running:
            self._stop()
            self._running = False
            self._text = ""

    def _start(self, text: str) -> None:
        from jnius import autoclass

        Intent = autoclass("android.content.Intent")
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        intent = Intent(activity, autoclass(_SERVICE))
        intent.putExtra("text", text)
        if autoclass("android.os.Build$VERSION").SDK_INT >= 26:
            activity.startForegroundService(intent)  # 8.0+ 须 5s 内 startForeground
        else:
            activity.startService(intent)

    def _stop(self) -> None:
        from jnius import autoclass

        Intent = autoclass("android.content.Intent")
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        activity.stopService(Intent(activity, autoclass(_SERVICE)))


keepAlive = AndroidKeepAlive()


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
