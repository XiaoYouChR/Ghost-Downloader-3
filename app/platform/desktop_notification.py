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
    QCoreApplication, QEasingCurve, QEvent, QFileInfo, QPoint, QPointF, QPropertyAnimation, QRectF,
    QResource, QStandardPaths, Qt, QTimer, Signal as QtSignal,
)
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPixmap, QScreen
from PySide6.QtWidgets import QFileIconProvider, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentIcon, IconWidget, InfoBarIcon, PushButton, StrongBodyLabel,
    TransparentToolButton, isDarkTheme, qconfig, setCustomStyleSheet,
)

from app.platform.desktop import openFile, revealInFolder
from app.platform.windows import isGreaterEqualWin11
from app.signal import Signal

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from app.models.task import Task, TaskError
    from app.services.browser_service import PairRequest

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
TEXT_WIDTH = WIDTH - 2 * PADDING - FILE_ICON_SIZE - ICON_SPACING
STATUS_ICON_SIZE = 32
CORNER_RADIUS = 8
DEFAULT_DURATION = 5
SOUND_INTERVAL = 1.0
ENTER_DURATION, EXIT_DURATION, MOVE_DURATION = 333, 167, 250

# 浅色亚克力下使用半透明磨砂白按钮以融入卡片；深色模式保持原版 dark/button.qss
LIGHT_ACTION_BUTTON_QSS = """
PushButton {
    background: rgba(255, 255, 255, 0.45);
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-bottom: 1px solid rgba(0, 0, 0, 0.14);
    border-radius: 5px;
    color: rgba(0, 0, 0, 0.90);
    padding: 5px 12px 6px 12px;
    outline: none;
}
PushButton:hover {
    background: rgba(255, 255, 255, 0.65);
    border: 1px solid rgba(0, 0, 0, 0.10);
    border-bottom: 1px solid rgba(0, 0, 0, 0.16);
    color: #000000;
}
PushButton:pressed {
    background: rgba(0, 0, 0, 0.05);
    border: 1px solid rgba(0, 0, 0, 0.08);
    color: rgba(0, 0, 0, 0.63);
}
PushButton:disabled {
    background: rgba(255, 255, 255, 0.25);
    border: 1px solid rgba(0, 0, 0, 0.05);
    color: rgba(0, 0, 0, 0.36);
}
""".strip()


def applyActionButtonStyle(button: PushButton) -> None:
    setCustomStyleSheet(button, LIGHT_ACTION_BUTTON_QSS, "")


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
        message=f"{task.name}\n" + QCoreApplication.translate(
            "Notifications", "大小 {0}，保存于 {1}").format(toReadableSize(task.fileSize), task.outputFolder),
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
        message=QCoreApplication.translate("Notifications", "任务未自动开始\n剩余 {0}，需要 {1}").format(
            toReadableSize(free), toReadableSize(needed)),
        urgency=Urgency.Critical,
        on_clicked=activate,
        timeout=0,
    )


def buildParseFailed(url: str, error: TaskError, activate: Callable[[], None]) -> Notification:
    from app.i18n import toLocalizedError

    return Notification(
        title=QCoreApplication.translate("Notifications", "链接解析失败"),
        message=f"{url}\n{toLocalizedError(error)}",
        urgency=Urgency.Critical,
        on_clicked=activate,
        timeout=0,
    )


def buildTaskFailed(task: Task, activate: Callable[[], None]) -> Notification:
    from app.i18n import toLocalizedError

    error = toLocalizedError(task.lastError) if task.lastError else ""
    return Notification(
        title=QCoreApplication.translate("Notifications", "下载失败"),
        message=f"{task.name}\n{error}",
        urgency=Urgency.Critical,
        on_clicked=activate,
        timeout=0,
    )


def buildClipboardRequest(urls: list[str], accept: Callable[[], None]) -> Notification:
    message = urls[0]
    if len(urls) > 1:
        message += "\n" + QCoreApplication.translate("Notifications", "等 {0} 个链接").format(len(urls))
    return Notification(
        title=QCoreApplication.translate("Notifications", "检测到下载链接"),
        message=message,
        buttons=(
            Button(title=QCoreApplication.translate("Notifications", "下载"), on_pressed=accept),
            Button(title=QCoreApplication.translate("Notifications", "忽略"), on_pressed=None),
        ),
        on_clicked=accept,
    )


def buildPairRequest(request: PairRequest, approve: Callable[[], None], reject: Callable[[], None]) -> Notification:
    client = request.clientKind or QCoreApplication.translate("Notifications", "浏览器扩展")
    version = request.extensionVersion or QCoreApplication.translate("Notifications", "未知")
    return Notification(
        title=QCoreApplication.translate("Notifications", "浏览器扩展配对请求"),
        message="\n".join((
            QCoreApplication.translate("Notifications", "{0} {1} 请求连接").format(client, version),
            QCoreApplication.translate("Notifications", "来源: {0}").format(request.peerAddress),
            QCoreApplication.translate("Notifications", "仅在你刚刚点击扩展里的\"自动配对\"时允许"),
        )),
        buttons=(
            Button(title=QCoreApplication.translate("Notifications", "允许配对"), on_pressed=approve),
            Button(title=QCoreApplication.translate("Notifications", "拒绝"), on_pressed=reject),
        ),
        on_dismissed=reject,
        timeout=0,
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


class DoNotDisturb:
    changed = Signal()

    def isOn(self) -> bool:
        return False

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

    class WindowsDoNotDisturb(QAbstractNativeEventFilter, DoNotDisturb):
        def __init__(self):
            super().__init__()
            self._window = QWindow()
            self._window.create()
            self._hwnd = int(self._window.winId())
            QCoreApplication.instance().installNativeEventFilter(self)
            shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(self._appbarData()))
            if not wtsapi32.WTSRegisterSessionNotification(self._hwnd, 0):
                logger.warning("注册会话通知失败: {}", ctypes.GetLastError())

        def isOn(self) -> bool:
            buffer, size = ctypes.c_void_p(), wintypes.DWORD()
            if wtsapi32.WTSQuerySessionInformationW(
                    None, WTS_CURRENT_SESSION, WTS_SESSION_INFO_EX, ctypes.byref(buffer), ctypes.byref(size)):
                # WTSINFOEXW.Data.WTSInfoExLevel1.SessionFlags
                isLocked = ctypes.c_int32.from_address(buffer.value + 16).value == WTS_SESSIONSTATE_LOCK
                wtsapi32.WTSFreeMemory(buffer)
                if isLocked:
                    return True
            state = ctypes.c_int()
            if shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
                return False
            return state.value in (QUNS_BUSY, QUNS_RUNNING_D3D_FULL_SCREEN, QUNS_PRESENTATION_MODE)

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

    class LinuxDoNotDisturb(QObject, DoNotDisturb):
        def __init__(self, path: str):
            super().__init__()
            self._path = path
            QDBusConnection.systemBus().connect(
                LOGIND, path, PROPERTIES, "PropertiesChanged", self, PROPERTIES_CHANGED_SLOT)

        def isOn(self) -> bool:
            message = QDBusMessage.createMethodCall(LOGIND, self._path, PROPERTIES, "Get")
            message.setArguments([f"{LOGIND}.Session", "LockedHint"])
            reply = QDBusConnection.systemBus().call(message)
            if reply.type() == QDBusMessage.MessageType.ErrorMessage:
                return False
            return bool(reply.arguments()[0].variant())

        def close(self) -> None:
            QDBusConnection.systemBus().disconnect(
                LOGIND, self._path, PROPERTIES, "PropertiesChanged", self, PROPERTIES_CHANGED_SLOT)

        @Slot(str, "QVariantMap", "QStringList")
        def onPropertiesChanged(self, interface: str, changed: dict, invalidated: list) -> None:
            if "LockedHint" in changed or "LockedHint" in invalidated:
                self.changed.emit()


def createDoNotDisturb() -> DoNotDisturb:
    if sys.platform == "win32":
        return WindowsDoNotDisturb()
    if sys.platform == "linux":
        message = QDBusMessage.createMethodCall(LOGIND, "/org/freedesktop/login1", f"{LOGIND}.Manager", "GetSession")
        message.setArguments(["auto"])
        reply = QDBusConnection.systemBus().call(message)
        if reply.type() != QDBusMessage.MessageType.ErrorMessage:
            return LinuxDoNotDisturb(reply.arguments()[0].path())
        logger.debug("logind 不可用，Popup 不判断锁屏: {}", reply.errorMessage())
    return DoNotDisturb()


class Popup(QWidget):
    exited = QtSignal()
    dismissed = QtSignal()
    clicked = QtSignal()
    layoutChanged = QtSignal()
    hasTaskbarButton = False

    def __init__(self):
        super().__init__()
        self.popupId: str | None = None
        self.openOnTaskbar = False
        self.duration = 0
        self.hasSound = False
        self.isExiting = False
        self._isHovered = False
        self._targetPos = QPoint()
        self._pressX: float | None = None

    @property
    def isLongLived(self) -> bool:
        return self.duration == 0

    def _initWidget(self) -> None:
        from app.startup import syncTheme
        syncTheme()
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setWindowFlags(flags if self.hasTaskbarButton else flags | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_X11DoNotAcceptFocus)
        self._isAcrylic = isGreaterEqualWin11()
        if sys.platform != "win32" or self._isAcrylic:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(WIDTH)
        self.windowEffect = None
        if sys.platform == "win32":
            from qframelesswindow import WindowEffect

            from app.platform.taskbar import addTaskbarButton
            if self.hasTaskbarButton:
                addTaskbarButton(int(self.winId()))
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
        self.closeButton = self._createHeaderButton(FluentIcon.CLOSE)
        self.headerButtons = [self.closeButton]

        self.closeTimer = QTimer(self)
        self.closeTimer.setSingleShot(True)
        self.moveAnimation = QPropertyAnimation(self, b"pos", self)

    def _initLayout(self) -> None:
        self.headerLayout = QHBoxLayout()
        self.headerLayout.setContentsMargins(0, 0, 0, 0)
        self.headerLayout.setSpacing(SPACING)
        self.headerLayout.addWidget(self.logoLabel)
        self.headerLayout.addWidget(self.appNameLabel)
        self.headerLayout.addStretch(1)
        for button in self.headerButtons:
            self.headerLayout.addWidget(button)

        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(PADDING, PADDING // 2, PADDING // 2, PADDING)
        self.vBoxLayout.setSpacing(SPACING)
        self.vBoxLayout.addLayout(self.headerLayout)

    def _bind(self) -> None:
        self.moveAnimation.finished.connect(self._onMoveAnimationFinished)
        self.closeButton.clicked.connect(lambda: self.exit(isDismissed=True))
        self.closeTimer.timeout.connect(lambda: self.exit(isDismissed=True))
        qconfig.themeChanged.connect(self._onThemeChanged)

    def _createHeaderButton(self, icon: FluentIcon) -> TransparentToolButton:
        button = TransparentToolButton(icon, self)
        button.setFixedSize(32, 32)
        button.setIconSize(button.iconSize() * 0.75)
        policy = button.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        button.setSizePolicy(policy)
        button.hide()
        return button

    def _toPixmap(self, pixmap: QPixmap, size: int) -> QPixmap:
        ratio = self.devicePixelRatioF()
        scaled = pixmap.scaled(round(size * ratio), round(size * ratio),
                               Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        scaled.setDevicePixelRatio(ratio)
        return scaled

    def moveTo(self, pos: QPoint) -> None:
        isMoved = pos != self._targetPos
        self._targetPos = pos
        if self.windowState() & Qt.WindowState.WindowMinimized:
            return
        if self.openOnTaskbar:
            self.openOnTaskbar = False
            self._detachFromActiveWindow()
            if sys.platform == "win32":
                from app.platform.taskbar import minimizeWithoutActivating
                minimizeWithoutActivating(int(self.winId()), pos.x(), pos.y(), self.width(), self.height())
                return
            self.move(pos)
            self.showMinimized()
            return
        if not self.isVisible():
            self._detachFromActiveWindow()
            self.move(pos.x() + self.width() + SCREEN_MARGIN, pos.y())
            self.show()
            self._animate(pos, ENTER_DURATION, ENTER_CURVE)
            self._restartTimer()
        elif isMoved and self._pressX is None:
            self._animate(pos, MOVE_DURATION, MOVE_CURVE)

    def _detachFromActiveWindow(self) -> None:
        self.winId()
        if handle := self.windowHandle():
            handle.setTransientParent(None)

    def showAt(self, pos: QPoint) -> None:
        self._targetPos = pos
        self.move(pos)
        self.show()
        self._setHovered(self.geometry().contains(QCursor.pos()))
        self._restartTimer()

    def exit(self, isDismissed: bool) -> None:
        if self.isExiting:
            return
        self.isExiting = True
        self.closeTimer.stop()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        if isDismissed:
            self.dismissed.emit()
        self._animate(QPoint(self._targetPos.x() + self.width() + SCREEN_MARGIN, self.y()),
                      EXIT_DURATION, EXIT_CURVE)

    def _animate(self, pos: QPoint, duration: int, curve: QEasingCurve) -> None:
        self.moveAnimation.stop()
        isAnimated = not self.isMinimized()
        if isAnimated and sys.platform == "win32":
            value = wintypes.BOOL(True)
            user32.SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(value), 0)
            isAnimated = bool(value.value)
        if not isAnimated:
            self.move(pos)
            QTimer.singleShot(0, self, self._onMoveAnimationFinished)
            return
        self.moveAnimation.setDuration(duration)
        self.moveAnimation.setEasingCurve(curve)
        self.moveAnimation.setStartValue(self.pos())
        self.moveAnimation.setEndValue(pos)
        self.moveAnimation.start()

    def _restartTimer(self) -> None:
        if self.duration > 0 and not self._isHovered and not self.isExiting:
            self.closeTimer.start(self.duration * 1000)

    def _onMoveAnimationFinished(self) -> None:
        if self.isExiting:
            self.exited.emit()

    def _onThemeChanged(self) -> None:
        self._applyAcrylic()
        self.update()

    def _applyAcrylic(self) -> None:
        if self._isAcrylic:
            self.windowEffect.setAcrylicEffect(self.winId(), "20202030" if isDarkTheme() else "F5F5F5A6")

    def showEvent(self, event) -> None:
        from app.startup import syncTheme
        if syncTheme():
            self._onThemeChanged()
        super().showEvent(event)
        # 显示前写入的还原坐标还没落到正确屏幕上
        if event.spontaneous() and not self.isMinimized():
            self.move(self._targetPos)

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.WindowStateChange:
            self.layoutChanged.emit()
        super().changeEvent(event)

    def closeEvent(self, event) -> None:
        if event.spontaneous():
            event.ignore()
            self.exit(isDismissed=True)
            return
        self.closeTimer.stop()
        self.moveAnimation.stop()
        if self.hasTaskbarButton and sys.platform == "win32":
            from app.platform.taskbar import setWindowAppId
            setWindowAppId(int(self.winId()), None)
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

    def _setHovered(self, isHovered: bool) -> None:
        self._isHovered = isHovered
        for button in self.headerButtons:
            button.setVisible(isHovered)
        self.update()
        if isHovered:
            self.closeTimer.stop()
        else:
            self._restartTimer()

    def enterEvent(self, event) -> None:
        self._setHovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._setHovered(False)
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
        super().mouseReleaseEvent(event)
        if event.button() != Qt.MouseButton.LeftButton or self._pressX is None:
            return
        offset = event.globalPosition().x() - self._pressX
        self._pressX = None
        if offset > self.width() / 3:
            self.exit(isDismissed=True)
        elif offset > 4:
            self._animate(self._targetPos, MOVE_DURATION, MOVE_CURVE)
        else:
            self.clicked.emit()


class NotificationPopup(Popup):
    def __init__(self, notification: Notification):
        super().__init__()
        self._notification = notification
        self.duration = DEFAULT_DURATION if notification.timeout == -1 else notification.timeout
        if notification.timeout == -1 and sys.platform == "win32":
            seconds = wintypes.ULONG(DEFAULT_DURATION)
            user32.SystemParametersInfoW(SPI_GETMESSAGEDURATION, 0, ctypes.byref(seconds), 0)
            self.duration = seconds.value
        self.hasSound = notification.sound is not None
        self._initWidget()
        self._initLayout()
        self._bind()

    def _initWidget(self) -> None:
        super()._initWidget()
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

        lines = self._notification.message.splitlines() or [""]
        self.titleLabel = StrongBodyLabel(self._notification.title, self)
        self.bodyLabel = BodyLabel(self)
        self.bodyLabel.setText(self.bodyLabel.fontMetrics().elidedText(lines[0], Qt.TextElideMode.ElideMiddle, TEXT_WIDTH))
        self.bodyLabel.setToolTip(lines[0])
        self.detailLabels = []
        for line in lines[1:3]:
            label = CaptionLabel(self)
            label.setText(label.fontMetrics().elidedText(line, Qt.TextElideMode.ElideRight, TEXT_WIDTH))
            label.setTextColor(QColor(0, 0, 0, 165), QColor(255, 255, 255, 155))
            self.detailLabels.append(label)

        self.buttons = []
        for button in self._notification.buttons:
            pushButton = PushButton(button.title, self)
            pushButton.setFixedHeight(32)
            pushButton.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            applyActionButtonStyle(pushButton)
            self.buttons.append((pushButton, button))

    def _initLayout(self) -> None:
        super()._initLayout()
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
        self.vBoxLayout.addLayout(content)

        if self.buttons:
            buttons = QHBoxLayout()
            buttons.setContentsMargins(0, SPACING, PADDING // 2, 0)
            buttons.setSpacing(SPACING)
            for pushButton, _ in self.buttons:
                buttons.addWidget(pushButton)
            self.vBoxLayout.addLayout(buttons)
        self.adjustSize()

    def _bind(self) -> None:
        super()._bind()
        for pushButton, button in self.buttons:
            pushButton.clicked.connect(lambda _=False, b=button: self._onActivated(b.on_pressed))
        if onClicked := self._notification.on_clicked:
            self.clicked.connect(lambda: self._onActivated(onClicked))
        if onDismissed := self._notification.on_dismissed:
            self.dismissed.connect(lambda: QTimer.singleShot(0, onDismissed))

    def _onActivated(self, callback: Callable[[], None] | None) -> None:
        self.exit(isDismissed=False)
        if callback:
            QTimer.singleShot(0, callback)


class PopupStack:
    def __init__(self, doNotDisturb: DoNotDisturb):
        self._doNotDisturb = doNotDisturb
        self._popups: list[Popup] = []  # 没有 parent，窗口靠这份列表活着
        self._pending: deque[Popup] = deque()
        self._lastSoundAt = float("-inf")
        self._isClosed = False
        doNotDisturb.changed.connect(self._showPending)
        application = QGuiApplication.instance()
        application.primaryScreenChanged.connect(self._onPrimaryScreenChanged)
        application.screenAdded.connect(self._onScreenAdded)
        for screen in application.screens():
            self._onScreenAdded(screen)

    def add(self, popup: Popup, replacing: Popup | None = None) -> None:
        if self._isClosed:
            popup.deleteLater()
            return
        if replacing is None and popup.popupId:
            replacing = self._byId(popup.popupId)
        popup.exited.connect(lambda: self._remove(popup))
        popup.layoutChanged.connect(self._arrange)
        if replacing in self._pending:
            self._pending[self._pending.index(replacing)] = popup
            self._close(replacing)
            return
        if replacing in self._popups and not replacing.isExiting:
            self._popups[self._popups.index(replacing)] = popup
            if replacing.isVisible() and not replacing.isMinimized():
                popup.showAt(replacing.pos())
            self._close(replacing)
            self._playSound(popup)
            self._arrange()
            return
        self._pending.append(popup)
        self._showPending()

    def has(self, popupId: str) -> bool:
        return self._byId(popupId) is not None

    def popup(self, popupId: str) -> Popup | None:
        return self._byId(popupId)

    def countShown(self, prefix: str) -> int:
        return sum(1 for popup in self._popups
                   if not popup.isExiting and not popup.isMinimized()
                   and (popup.popupId or "").startswith(prefix))

    def count(self, prefix: str) -> int:
        return sum(1 for popup in (*self._pending, *self._popups)
                   if not popup.isExiting and (popup.popupId or "").startswith(prefix))

    def close(self, popupId: str) -> None:
        popup = self._byId(popupId)
        if popup is None:
            return
        if popup in self._pending:
            self._pending.remove(popup)
            self._close(popup)
            return
        popup.exit(isDismissed=False)

    def _byId(self, popupId: str) -> Popup | None:
        for popup in (*self._pending, *self._popups):
            if popup.popupId == popupId and not popup.isExiting:
                return popup
        return None

    def clear(self) -> None:
        self._isClosed = True
        for popup in [*self._pending, *self._popups]:
            self._close(popup)
        self._pending.clear()
        self._popups.clear()

    def _showPending(self) -> None:
        if not self._pending or QGuiApplication.primaryScreen() is None or self._doNotDisturb.isOn():
            return
        while self._pending:
            popup = self._pending.popleft()
            self._popups.append(popup)
            self._playSound(popup)
        self._arrange()

    def _playSound(self, popup: Popup) -> None:
        if not popup.hasSound or time.monotonic() - self._lastSoundAt < SOUND_INTERVAL:
            return
        self._lastSoundAt = time.monotonic()
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
        shown = [p for p in self._popups if not p.isExiting and not p.isMinimized()]
        isFull = False
        for popup in [*reversed([p for p in shown if p.isLongLived]),
                      *reversed([p for p in shown if not p.isLongLived])]:
            y = bottom - popup.height()
            if not popup.isLongLived and (isFull or y < top):
                isFull = True
                popup.exit(isDismissed=True)
                continue
            popup.moveTo(QPoint(right - popup.width(), y))
            bottom = y - SPACING

    def _remove(self, popup: Popup) -> None:
        if popup not in self._popups:
            return
        self._popups.remove(popup)
        self._close(popup)
        self._arrange()

    def _close(self, popup: Popup) -> None:
        popup.isExiting = True
        popup.close()
        popup.deleteLater()

    def _onScreenAdded(self, screen: QScreen) -> None:
        # 每块屏只在加入时连一次，副屏变化时多排一次无害
        screen.availableGeometryChanged.connect(self._arrange)

    def _onPrimaryScreenChanged(self, _screen: QScreen | None) -> None:
        self._arrange()
        self._showPending()


class PopupNotifier:
    def __init__(self, stack: PopupStack):
        self._stack = stack

    def send(self, notification: Notification, popupId: str | None = None) -> None:
        popup = NotificationPopup(notification)
        popup.popupId = popupId
        self._stack.add(popup)

