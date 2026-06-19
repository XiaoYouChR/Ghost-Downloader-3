import sys
from pathlib import Path
from signal import signal, SIGINT

from PySide6.QtCore import QSharedMemory, QEvent, QBuffer, QByteArray, QRectF, Qt
from PySide6.QtGui import QFileOpenEvent, QPixmap, QPainter, QColor, QFontMetricsF
from PySide6.QtWidgets import QApplication
from loguru import logger

from app.supports.android import IS_ANDROID
from app.supports.config import cfg, DESKTOP_ID, DESKTOP_OBJECT_PATH
from app.supports.signal_bus import signalBus
from app.supports.utils import toReadableSize

if sys.platform == "darwin":
    from AppKit import (
        NSApp,
        NSApplication,
        NSApplicationActivationPolicyAccessory,
        NSApplicationActivationPolicyRegular,
        NSImage,
        NSImageView,
    )
    from Foundation import NSData


def toDockTileImage(base: QPixmap, speedText: str) -> QPixmap:
    size = base.width()
    canvas = QPixmap(base)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    margin = size * 0.11
    bandHeight = size * 0.24
    band = QRectF(margin * 1.3, size - margin - bandHeight, size - margin * 2.6, bandHeight)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(0, 0, 0, 165))
    painter.drawRoundedRect(band, bandHeight / 2, bandHeight / 2)

    font = painter.font()
    font.setBold(True)
    pixel = bandHeight * 0.5
    font.setPixelSize(int(pixel))
    while QFontMetricsF(font).horizontalAdvance(speedText) > band.width() * 0.88 and pixel > 6:
        pixel -= 1
        font.setPixelSize(int(pixel))
    painter.setFont(font)
    painter.setPen(QColor(255, 255, 255))
    painter.drawText(band, Qt.AlignmentFlag.AlignCenter, speedText)

    painter.end()
    return canvas


class SingletonApplication(QApplication):

    def __init__(self, argv: list[str], key: str):
        super().__init__(argv)
        self.key = key
        self._lockSingleInstance()

        try:
            signal(SIGINT, self._onInterrupt)
        except Exception as e:
            logger.warning(f"Failed to register SIGINT handler: {e}")

        if sys.platform == "darwin":
            self._dockBaseIcon: QPixmap | None = None
            self._dockImageView = None  # NSImageView 强引用, 防 ObjC 侧释放
            self._setDockIconVisible(cfg.showDockIcon.value, activate=False)
            cfg.showDockIcon.valueChanged.connect(self._onShowDockIconChanged)
            signalBus.globalSpeedChanged.connect(self._onGlobalSpeedChanged)
            cfg.showDockSpeed.valueChanged.connect(self._onShowDockSpeedChanged)
        if sys.platform == "linux" and not IS_ANDROID:
            self._listenOnDesktopBus()

    def _lockSingleInstance(self) -> None:
        if IS_ANDROID:
            self.memory = None
            return
        # 清掉 unix 上崩溃残留的共享内存段
        try:
            cleanupMemory = QSharedMemory(self.key)
            if cleanupMemory.attach():
                cleanupMemory.detach()
        except Exception as e:
            logger.warning(f"Failed to cleanup shared memory: {e}")

        self.memory = QSharedMemory()
        self.memory.setKey(self.key)

        if self.memory.attach():  # attach 成功即已有实例: 转交本次启动后自退
            if sys.platform in ("win32", "linux"):
                from app.supports.file_open import sendToRunningInstance
                sendToRunningInstance()
            sys.exit(-1)

        if not self.memory.create(1):
            e = RuntimeError(self.memory.errorString())
            logger.opt(exception=e).error("Failed to create shared memory")
            try:
                self.memory.attach()
                self.memory.detach()
                if not self.memory.create(1):
                    raise RuntimeError(self.memory.errorString())
            except Exception as e:
                logger.opt(exception=e).error("Failed to recover from shared memory error")
                raise RuntimeError(self.memory.errorString())

    def _unlockSingleInstance(self) -> None:
        if self.memory is None:
            return
        try:
            if self.memory.isAttached():
                self.memory.detach()
        except Exception as e:
            logger.warning(f"Failed to cleanup shared memory: {e}")

    def exec(self):
        try:
            return super().exec()
        finally:
            self._unlockSingleInstance()

    def quit(self):
        self._unlockSingleInstance()
        super().quit()

    def _onInterrupt(self, _signum, _frame):
        logger.error("KeyboardInterrupt, quitting application")
        self.quit()

    def _setDockIconVisible(self, visible: bool, activate: bool = False):
        if sys.platform != "darwin":
            return

        app = NSApp or NSApplication.sharedApplication()
        policy = (
            NSApplicationActivationPolicyRegular
            if visible
            else NSApplicationActivationPolicyAccessory
        )
        app.setActivationPolicy_(policy)
        if activate:
            app.activateIgnoringOtherApps_(True)

    def _onShowDockIconChanged(self, visible: bool) -> None:
        self._setDockIconVisible(visible, activate=True)
        self._restoreDockTile()  # 可见性切换后旧 tile 视图作废, 下次渲染重新挂载

    def _onGlobalSpeedChanged(self, speed: int) -> None:
        if not (cfg.showDockSpeed.value and cfg.showDockIcon.value):
            return
        if speed <= 0:
            self._restoreDockTile()
            return
        self._renderDockTile(f"{toReadableSize(speed)}/s")

    def _onShowDockSpeedChanged(self, enabled: bool) -> None:
        # 关 -> 立刻还原; 开 -> 等下一次 globalSpeedChanged 自然画上
        if not enabled:
            self._restoreDockTile()

    def _renderDockTile(self, text: str) -> None:
        if self._dockBaseIcon is None:
            self._dockBaseIcon = QPixmap(":/image/logo_macOS.png").scaled(
                256, 256,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        image = toDockTileImage(self._dockBaseIcon, text)

        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QBuffer.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        buffer.close()
        nsImage = NSImage.alloc().initWithData_(
            NSData.dataWithBytes_length_(data.data(), data.size())
        )

        tile = (NSApp or NSApplication.sharedApplication()).dockTile()
        if self._dockImageView is None:
            self._dockImageView = NSImageView.alloc().init()
            tile.setContentView_(self._dockImageView)
        self._dockImageView.setImage_(nsImage)
        tile.display()

    def _restoreDockTile(self) -> None:
        if self._dockImageView is None:
            return
        tile = (NSApp or NSApplication.sharedApplication()).dockTile()
        tile.setContentView_(None)
        tile.display()
        self._dockImageView = None

    def _listenOnDesktopBus(self) -> None:
        from PySide6.QtDBus import QDBusConnection
        from app.supports.file_open import DesktopBusReceiver

        bus = QDBusConnection.sessionBus()
        if not bus.registerService(DESKTOP_ID):
            return
        self._dbusObject = DesktopBusReceiver()
        bus.registerObject(
            DESKTOP_OBJECT_PATH,
            self._dbusObject,
            QDBusConnection.RegisterOption.ExportAllSlots,
        )

    def event(self, e: QEvent) -> bool:
        if isinstance(e, QFileOpenEvent):
            uri = e.url().toString() if not e.url().isEmpty() else Path(e.file()).as_uri()
            if uri:
                signalBus.openFileRequested.emit([uri])
            return True

        if sys.platform == "darwin" and e.type() == QEvent.Type.ApplicationActivate:
            signalBus.showMainWindow.emit()

        return super().event(e)
