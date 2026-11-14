from __future__ import annotations

import shutil
import subprocess
import sys
import time
from collections import deque
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from desktop_notifier.common import DEFAULT_SOUND, Button, Icon, Notification, Sound, Urgency
from loguru import logger
from PySide6.QtCore import (
    QCoreApplication, QEasingCurve, QFileInfo, QPoint, QPointF, QPropertyAnimation, QRectF,
    QResource, QStandardPaths, Qt, QTimer, Signal as QtSignal,
)
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPixmap, QScreen
from PySide6.QtWidgets import QFileIconProvider, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentIcon, IconWidget, InfoBarIcon, PushButton, StrongBodyLabel,
    TransparentToolButton, isDarkTheme, qconfig,
)

from app.platform.desktop import openFile, revealInFolder
from app.platform.windows import isGreaterEqualWin11
from app.signal import Signal

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from app.models.task import Task, TaskError

APP_NAME = "Ghost Downloader"
LOGO_RESOURCE = ":/image/logo.png"
SOUND_RESOURCE = ":/res/completed_task.wav"
COMPLETE_SOUND = Sound(name="complete")

WIDTH = 364
PADDING = 16
SCREEN_MARGIN = 12
SPACING = 8
ICON_SPACING = 12
FILE_ICON_SIZE = 48
STATUS_ICON_SIZE = 32
CORNER_RADIUS = 8
DEFAULT_DURATION = 5
SOUND_INTERVAL = 1.0
ENTER_DURATION, EXIT_DURATION, MOVE_DURATION = 333, 167, 250


def toEasingCurve(x1: float, y1: float, x2: float, y2: float) -> QEasingCurve:
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(QPointF(x1, y1), QPointF(x2, y2), QPointF(1, 1))
    return curve


ENTER_CURVE, EXIT_CURVE, MOVE_CURVE = toEasingCurve(0, 0, 0, 1), toEasingCurve(1, 0, 1, 1), toEasingCurve(0.55, 0.55, 0, 1)


def extractResource(resource: str) -> Path:
    # 临时目录会被系统定期清理，不能只释放一次
    path = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation), f"gd_{Path(resource).name}")
    data = QResource(resource).data()
    if not path.exists() or path.stat().st_size != len(data):
        path.write_bytes(data)
    return path


def toFileIcon(path: str) -> Icon | None:
    # 系统通知异步读图标，固定文件名会被下一个任务覆盖
    suffix = Path(path).suffix.lstrip(".").lower() or "folder"
    iconPath = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation), f"gd_icon_{suffix}.png")
    pixmap = QFileIconProvider().icon(QFileInfo(path)).pixmap(48, 48).scaled(
        128, 128, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    if pixmap.isNull() or not pixmap.save(str(iconPath), "PNG"):
        logger.debug("提取文件图标失败: {}", path)
        return None
    return Icon(path=iconPath)


def buildTaskCompleted(task: Task, icon: Icon | None) -> Notification:
    from app.format import toReadableSize

    outputPath = task.outputPath
    return Notification(
        title=QCoreApplication.translate("Notifications", "下载完成"),
        message=f"{task.name}\n{toReadableSize(task.fileSize)} · {task.outputFolder}",
        icon=icon,
        buttons=(
            Button(title=QCoreApplication.translate("Notifications", "打开文件"),
                   on_pressed=lambda: openFile(outputPath)),
            Button(title=QCoreApplication.translate("Notifications", "打开文件夹"),
                   on_pressed=lambda: revealInFolder(outputPath)),
        ),
        on_clicked=lambda: openFile(outputPath),
        sound=COMPLETE_SOUND,
    )


def buildDiskSpaceInsufficient(free: int, needed: int, activate: Callable[[], None]) -> Notification:
    from app.format import toReadableSize

    return Notification(
        title=QCoreApplication.translate("Notifications", "磁盘空间不足"),
        message=QCoreApplication.translate("Notifications", "任务已加入等待队列\n剩余 {0}，需要 {1}").format(
            toReadableSize(free), toReadableSize(needed)),
        urgency=Urgency.Critical,
        on_clicked=activate,
    )


def buildParseFailed(url: str, error: TaskError, activate: Callable[[], None]) -> Notification:
    from app.i18n import toLocalizedError

    return Notification(
        title=QCoreApplication.translate("Notifications", "链接解析失败"),
        message=f"{url}\n{toLocalizedError(error)}",
        urgency=Urgency.Critical,
        on_clicked=activate,
    )


class SystemNotifier:
    def __init__(self, submit: Callable[[Coroutine], object]):
        self._submit = submit
        self._notifier = None

    def send(self, notification: Notification) -> None:
        # Windows 未打包的应用和 macOS 只能用系统默认提示音
        if notification.sound and sys.platform != "linux":
            notification = replace(notification, sound=DEFAULT_SOUND)
        self._submit(self._send(notification, extractResource(LOGO_RESOURCE)))

    async def _send(self, notification: Notification, logoPath: Path) -> None:
        # WinRT 后端要在 running loop 里构造
        if self._notifier is None:
            from desktop_notifier import DesktopNotifier
            self._notifier = DesktopNotifier(app_name=APP_NAME, app_icon=Icon(path=logoPath))
        await self._notifier.send_notification(notification)


class Presence:
    """能否打扰用户，见 ADR 0029。changed 只表示状态可能变了，要用 canInterrupt 重新查询。"""

    changed = Signal()

    def canInterrupt(self) -> bool:
        return True

    def close(self) -> None:
        pass


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    from PySide6.QtCore import QAbstractNativeEventFilter
    from PySide6.QtGui import QWindow

    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    wtsapi32 = ctypes.windll.wtsapi32
    wtsapi32.WTSQuerySessionInformationW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
    wtsapi32.WTSFreeMemory.argtypes = [ctypes.c_void_p]

    WM_APP = 0x8000
    WM_APPBAR = WM_APP + 1
    WM_WTSSESSION_CHANGE = 0x02B1
    WM_TASKBARCREATED = user32.RegisterWindowMessageW("TaskbarCreated")
    ABM_NEW, ABM_REMOVE, ABN_FULLSCREENAPP = 0, 1, 2
    WTS_SESSION_LOCK, WTS_SESSION_UNLOCK = 7, 8
    WTS_CURRENT_SESSION, WTS_SESSION_INFO_EX, WTS_SESSIONSTATE_LOCK = 0xFFFFFFFF, 25, 0
    QUNS_BUSY, QUNS_RUNNING_D3D_FULL_SCREEN, QUNS_PRESENTATION_MODE = 2, 3, 4
    SPI_GETCLIENTAREAANIMATION, SPI_GETMESSAGEDURATION = 0x1042, 0x2016

    class APPBARDATA(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uCallbackMessage", wintypes.UINT),
                    ("uEdge", wintypes.UINT), ("rc", wintypes.RECT), ("lParam", wintypes.LPARAM)]

    class WindowsPresence(QAbstractNativeEventFilter, Presence):
        def __init__(self):
            super().__init__()
            self._window = QWindow()
            self._window.create()
            self._hwnd = int(self._window.winId())
            QCoreApplication.instance().installNativeEventFilter(self)
            shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(self._appbarData()))
            if not wtsapi32.WTSRegisterSessionNotification(self._hwnd, 0):
                logger.warning("注册会话通知失败: {}", ctypes.GetLastError())

        def canInterrupt(self) -> bool:
            buffer, size = ctypes.c_void_p(), wintypes.DWORD()
            if wtsapi32.WTSQuerySessionInformationW(
                    None, WTS_CURRENT_SESSION, WTS_SESSION_INFO_EX, ctypes.byref(buffer), ctypes.byref(size)):
                # WTSINFOEXW.Data.WTSInfoExLevel1.SessionFlags
                isLocked = ctypes.c_int32.from_address(buffer.value + 16).value == WTS_SESSIONSTATE_LOCK
                wtsapi32.WTSFreeMemory(buffer)
                if isLocked:
                    return False
            state = ctypes.c_int()
            if shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
                return True
            return state.value not in (QUNS_BUSY, QUNS_RUNNING_D3D_FULL_SCREEN, QUNS_PRESENTATION_MODE)

        def close(self) -> None:
            shell32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(self._appbarData()))
            wtsapi32.WTSUnRegisterSessionNotification(self._hwnd)
            QCoreApplication.instance().removeNativeEventFilter(self)
            self._window.destroy()

        def _appbarData(self) -> APPBARDATA:
            data = APPBARDATA()
            data.cbSize = ctypes.sizeof(APPBARDATA)
            data.hWnd = self._hwnd
            data.uCallbackMessage = WM_APPBAR
            return data

        def nativeEventFilter(self, eventType, message):
            if bytes(eventType) != b"windows_generic_MSG":
                return False, 0
            msg = wintypes.MSG.from_address(int(message))
            if msg.hWnd != self._hwnd:
                return False, 0
            if msg.message == WM_APPBAR and msg.wParam == ABN_FULLSCREENAPP:
                self.changed.emit()
            elif msg.message == WM_WTSSESSION_CHANGE and msg.wParam in (WTS_SESSION_LOCK, WTS_SESSION_UNLOCK):
                self.changed.emit()
            elif msg.message == WM_TASKBARCREATED:
                shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(self._appbarData()))
            return False, 0


if sys.platform == "linux":
    from PySide6.QtCore import SLOT, QObject, Slot
    from PySide6.QtDBus import QDBusConnection, QDBusMessage

    LOGIND = "org.freedesktop.login1"
    PROPERTIES = "org.freedesktop.DBus.Properties"
    PROPERTIES_CHANGED_SLOT = SLOT("onPropertiesChanged(QString,QVariantMap,QStringList)")

    class LinuxPresence(QObject, Presence):
        def __init__(self, path: str):
            super().__init__()
            self._path = path
            QDBusConnection.systemBus().connect(
                LOGIND, path, PROPERTIES, "PropertiesChanged", self, PROPERTIES_CHANGED_SLOT)

        def canInterrupt(self) -> bool:
            message = QDBusMessage.createMethodCall(LOGIND, self._path, PROPERTIES, "Get")
            message.setArguments([f"{LOGIND}.Session", "LockedHint"])
            reply = QDBusConnection.systemBus().call(message)
            if reply.type() == QDBusMessage.MessageType.ErrorMessage:
                return True
            return not reply.arguments()[0].variant()

        def close(self) -> None:
            QDBusConnection.systemBus().disconnect(
                LOGIND, self._path, PROPERTIES, "PropertiesChanged", self, PROPERTIES_CHANGED_SLOT)

        @Slot(str, "QVariantMap", "QStringList")
        def onPropertiesChanged(self, interface: str, changed: dict, invalidated: list) -> None:
            if "LockedHint" in changed or "LockedHint" in invalidated:
                self.changed.emit()


def createPresence() -> Presence:
    if sys.platform == "win32":
        return WindowsPresence()
    if sys.platform == "linux":
        message = QDBusMessage.createMethodCall(LOGIND, "/org/freedesktop/login1", f"{LOGIND}.Manager", "GetSession")
        message.setArguments(["auto"])
        reply = QDBusConnection.systemBus().call(message)
        if reply.type() != QDBusMessage.MessageType.ErrorMessage:
            return LinuxPresence(reply.arguments()[0].path())
        logger.debug("logind 不可用，Popup 不判断锁屏: {}", reply.errorMessage())
    return Presence()


class Popup(QWidget):
    exited = QtSignal()

    def __init__(self, notification: Notification):
        super().__init__()
        self._notification = notification
        self._duration = DEFAULT_DURATION if notification.timeout == -1 else notification.timeout
        if notification.timeout == -1 and sys.platform == "win32":
            seconds = wintypes.ULONG(DEFAULT_DURATION)
            user32.SystemParametersInfoW(SPI_GETMESSAGEDURATION, 0, ctypes.byref(seconds), 0)
            self._duration = seconds.value
        self.isExiting = False
        self._isHovered = False
        self._targetPos = QPoint()
        self._pressX: float | None = None
        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                            | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_X11DoNotAcceptFocus)
        self._isAcrylic = isGreaterEqualWin11()
        if sys.platform != "win32" or self._isAcrylic:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(WIDTH)
        self.windowEffect = None
        if sys.platform == "win32":
            from qframelesswindow import WindowEffect
            self.windowEffect = WindowEffect(self)
            if self._isAcrylic:
                self._applyAcrylic()
                DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND = 33, 2
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    int(self.winId()), DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(ctypes.c_int(DWMWCP_ROUND)), 4)
            else:
                self.windowEffect.addMenuShadowEffect(self.winId())

        self.logoLabel = QLabel(self)
        self.logoLabel.setPixmap(self._toPixmap(QPixmap(LOGO_RESOURCE), 16))
        self.appNameLabel = CaptionLabel(APP_NAME, self)
        self.closeButton = TransparentToolButton(FluentIcon.CLOSE, self)
        self.closeButton.setFixedSize(32, 32)
        self.closeButton.setIconSize(self.closeButton.iconSize() * 0.75)
        policy = self.closeButton.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.closeButton.setSizePolicy(policy)
        self.closeButton.hide()

        icon = self._notification.icon
        if icon is not None and not (pixmap := QPixmap(str(icon.as_path()))).isNull():
            self.iconWidget = QLabel(self)
            self.iconWidget.setPixmap(self._toPixmap(pixmap, FILE_ICON_SIZE))
        elif self._notification.urgency == Urgency.Critical:
            self.iconWidget = IconWidget(InfoBarIcon.ERROR, self)
            self.iconWidget.setFixedSize(STATUS_ICON_SIZE, STATUS_ICON_SIZE)
        else:
            self.iconWidget = QLabel(self)
            self.iconWidget.setPixmap(self._toPixmap(QPixmap(LOGO_RESOURCE), FILE_ICON_SIZE))

        textWidth = WIDTH - 2 * PADDING - FILE_ICON_SIZE - ICON_SPACING
        lines = self._notification.message.splitlines() or [""]
        self.titleLabel = StrongBodyLabel(self._notification.title, self)
        self.bodyLabel = BodyLabel(self)
        self.bodyLabel.setText(self.bodyLabel.fontMetrics().elidedText(lines[0], Qt.TextElideMode.ElideMiddle, textWidth))
        self.bodyLabel.setToolTip(lines[0])
        self.detailLabels = []
        for line in lines[1:3]:
            label = CaptionLabel(self)
            label.setText(label.fontMetrics().elidedText(line, Qt.TextElideMode.ElideRight, textWidth))
            label.setTextColor(QColor(0, 0, 0, 155), QColor(255, 255, 255, 155))
            self.detailLabels.append(label)

        self.buttons = []
        for button in self._notification.buttons:
            pushButton = PushButton(button.title, self)
            pushButton.setFixedHeight(32)
            pushButton.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.buttons.append((pushButton, button))

        self.closeTimer = QTimer(self)
        self.closeTimer.setSingleShot(True)
        self.moveAnimation = QPropertyAnimation(self, b"pos", self)

    def _initLayout(self) -> None:
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(SPACING)
        header.addWidget(self.logoLabel)
        header.addWidget(self.appNameLabel)
        header.addStretch(1)
        header.addWidget(self.closeButton)

        texts = QVBoxLayout()
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(2)
        texts.addWidget(self.titleLabel)
        texts.addWidget(self.bodyLabel)
        for label in self.detailLabels:
            texts.addWidget(label)

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, PADDING // 2, 0)
        content.setSpacing(ICON_SPACING)
        content.addWidget(self.iconWidget, 0, Qt.AlignmentFlag.AlignTop)
        content.addLayout(texts, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(PADDING, PADDING // 2, PADDING // 2, PADDING)
        layout.setSpacing(SPACING)
        layout.addLayout(header)
        layout.addLayout(content)
        if self.buttons:
            buttons = QHBoxLayout()
            buttons.setContentsMargins(0, SPACING, PADDING // 2, 0)
            buttons.setSpacing(SPACING)
            for pushButton, _ in self.buttons:
                buttons.addWidget(pushButton)
            layout.addLayout(buttons)
        self.adjustSize()

    def _bind(self) -> None:
        self.moveAnimation.finished.connect(self._onMoveAnimationFinished)
        self.closeButton.clicked.connect(lambda: self.exit(isDismissed=True))
        self.closeTimer.timeout.connect(lambda: self.exit(isDismissed=True))
        for pushButton, button in self.buttons:
            pushButton.clicked.connect(lambda _=False, b=button: self._onButtonClicked(b))
        qconfig.themeChanged.connect(self._onThemeChanged)

    def _toPixmap(self, pixmap: QPixmap, size: int) -> QPixmap:
        ratio = self.devicePixelRatioF()
        scaled = pixmap.scaled(round(size * ratio), round(size * ratio),
                               Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        scaled.setDevicePixelRatio(ratio)
        return scaled

    def moveTo(self, pos: QPoint) -> None:
        """第一次从屏幕右侧滑入，之后平移到 pos。"""
        isMoved = pos != self._targetPos
        self._targetPos = pos
        if not self.isVisible():
            self.move(pos.x() + self.width() + SCREEN_MARGIN, pos.y())
            self.show()
            self._animate(pos, ENTER_DURATION, ENTER_CURVE)
            self._restartTimer()
        elif isMoved and self._pressX is None:
            self._animate(pos, MOVE_DURATION, MOVE_CURVE)

    def exit(self, isDismissed: bool) -> None:
        if self.isExiting:
            return
        self.isExiting = True
        self.closeTimer.stop()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        if isDismissed and self._notification.on_dismissed:
            self._notification.on_dismissed()
        self._animate(QPoint(self._targetPos.x() + self.width() + SCREEN_MARGIN, self.y()),
                      EXIT_DURATION, EXIT_CURVE)

    def _animate(self, pos: QPoint, duration: int, curve: QEasingCurve) -> None:
        self.moveAnimation.stop()
        isAnimated = True
        if sys.platform == "win32":
            value = wintypes.BOOL(True)
            user32.SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(value), 0)
            isAnimated = bool(value.value)
        if not isAnimated:
            self.move(pos)
            QTimer.singleShot(0, self._onMoveAnimationFinished)
            return
        self.moveAnimation.setDuration(duration)
        self.moveAnimation.setEasingCurve(curve)
        self.moveAnimation.setStartValue(self.pos())
        self.moveAnimation.setEndValue(pos)
        self.moveAnimation.start()

    def _restartTimer(self) -> None:
        if self._duration > 0 and not self._isHovered and not self.isExiting:
            self.closeTimer.start(self._duration * 1000)

    def _onButtonClicked(self, button: Button) -> None:
        if button.on_pressed:
            button.on_pressed()
        self.exit(isDismissed=False)

    def _onMoveAnimationFinished(self) -> None:
        if self.isExiting:
            self.exited.emit()

    def _onThemeChanged(self) -> None:
        self._applyAcrylic()
        self.update()

    def _applyAcrylic(self) -> None:
        if self._isAcrylic:
            self.windowEffect.setAcrylicEffect(self.winId(), "20202030" if isDarkTheme() else "FFFFFF30")

    def closeEvent(self, event) -> None:
        self.closeTimer.stop()
        self.moveAnimation.stop()
        super().closeEvent(event)

    def paintEvent(self, event) -> None:
        isDark = isDarkTheme()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = 0 if sys.platform == "win32" and not self._isAcrylic else CORNER_RADIUS
        if self._isAcrylic:
            # layered 窗口里全透明的像素会让鼠标点穿
            painter.fillRect(self.rect(), QColor(0, 0, 0, 1))
        else:
            painter.setBrush(QColor(44, 44, 44) if isDark else QColor(249, 249, 249))
            painter.setPen(QColor(255, 255, 255, 20) if isDark else QColor(0, 0, 0, 15))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        if self._isHovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 15) if isDark else QColor(0, 0, 0, 10))
            painter.drawRoundedRect(QRectF(self.rect()), radius, radius)

    def enterEvent(self, event) -> None:
        self._isHovered = True
        self.closeTimer.stop()
        self.closeButton.show()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._isHovered = False
        self.closeButton.hide()
        self.update()
        self._restartTimer()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressX = event.globalPosition().x()
            self.moveAnimation.stop()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._pressX is not None:
            offset = max(0, round(event.globalPosition().x() - self._pressX))
            self.move(self._targetPos.x() + offset, self._targetPos.y())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._pressX is None:
            return super().mouseReleaseEvent(event)
        offset = event.globalPosition().x() - self._pressX
        self._pressX = None
        if offset > self.width() / 3:
            self.exit(isDismissed=True)
        elif offset > 4:
            self._animate(self._targetPos, MOVE_DURATION, MOVE_CURVE)
        elif self._notification.on_clicked:
            self._notification.on_clicked()
            self.exit(isDismissed=False)
        super().mouseReleaseEvent(event)


class PopupNotifier:
    """只能在 Qt 主线程调用。"""

    def __init__(self, presence: Presence):
        self._presence = presence
        self._popups: list[Popup] = []  # 最早的在前；没有 parent 的窗口靠这里的引用存活
        self._pending: deque[Notification] = deque()
        self._lastSoundAt = float("-inf")
        self._isClosed = False
        presence.changed.connect(self._showPending)
        application = QGuiApplication.instance()
        application.primaryScreenChanged.connect(self._onPrimaryScreenChanged)
        application.screenAdded.connect(self._onScreenAdded)
        for screen in application.screens():
            self._onScreenAdded(screen)

    def send(self, notification: Notification) -> None:
        if self._isClosed:
            return
        self._pending.append(notification)
        self._showPending()

    def clear(self) -> None:
        """立即关闭全部 Popup，不触发 on_dismissed；之后的 send 一律忽略。"""
        self._isClosed = True
        self._pending.clear()
        for popup in self._popups:
            popup.close()
            popup.deleteLater()
        self._popups.clear()

    def _showPending(self) -> None:
        if not self._pending or QGuiApplication.primaryScreen() is None or not self._presence.canInterrupt():
            return
        while self._pending:
            notification = self._pending.popleft()
            popup = Popup(notification)
            popup.exited.connect(lambda p=popup: self._remove(p))
            self._popups.append(popup)
            if notification.sound and time.monotonic() - self._lastSoundAt >= SOUND_INTERVAL:
                self._lastSoundAt = time.monotonic()
                self._playSound()
        self._arrange()

    def _playSound(self) -> None:
        path = str(extractResource(SOUND_RESOURCE))
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            return
        for command in (("pw-play", "--media-role=Notification"),
                        ("paplay", "--property=media.role=event"),
                        ("canberra-gtk-play", "-f")):
            if executable := shutil.which(command[0]):
                subprocess.Popen([executable, *command[1:], path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
        logger.debug("找不到播放器，跳过提示音")

    def _arrange(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        right = area.x() + area.width() - SCREEN_MARGIN
        bottom = area.y() + area.height() - SCREEN_MARGIN
        top = area.y() + SCREEN_MARGIN
        isFull = False
        for popup in reversed([p for p in self._popups if not p.isExiting]):
            y = bottom - popup.height()
            if isFull or y < top:
                isFull = True
                popup.exit(isDismissed=True)
                continue
            popup.moveTo(QPoint(right - popup.width(), y))
            bottom = y - SPACING

    def _remove(self, popup: Popup) -> None:
        if popup not in self._popups:
            return
        self._popups.remove(popup)
        popup.close()
        popup.deleteLater()
        self._arrange()

    def _onScreenAdded(self, screen: QScreen) -> None:
        # 每块屏只在加入时连一次，副屏变化时多排一次无害
        screen.availableGeometryChanged.connect(self._arrange)

    def _onPrimaryScreenChanged(self, _screen: QScreen | None) -> None:
        self._arrange()
        self._showPending()
