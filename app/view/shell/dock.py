from PySide6.QtCore import QBuffer, QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPixmap

from AppKit import (
    NSApp, NSApplication, NSImage, NSImageView,
    NSApplicationActivationPolicyRegular, NSApplicationActivationPolicyAccessory,
)
from Foundation import NSData

from app.config.cfg import cfg
from app.format import toReadableSize
from app.services.speed_meter import speedMeter


def setDockIconVisible(visible: bool, activate: bool) -> None:
    app = NSApp or NSApplication.sharedApplication()
    app.setActivationPolicy_(
        NSApplicationActivationPolicyRegular if visible else NSApplicationActivationPolicyAccessory
    )
    if activate:
        app.activateIgnoringOtherApps_(True)


def setupDock() -> None:
    baseIcon = None
    imageView = None

    def render(text: str) -> None:
        nonlocal baseIcon, imageView

        if baseIcon is None:
            baseIcon = QPixmap(":/image/logo_macOS.png").scaled(
                256, 256,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        size = baseIcon.width()
        canvas = QPixmap(baseIcon)
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
        while QFontMetricsF(font).horizontalAdvance(text) > band.width() * 0.88 and pixel > 6:
            pixel -= 1
            font.setPixelSize(int(pixel))
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(band, Qt.AlignmentFlag.AlignCenter, text)
        painter.end()

        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QBuffer.OpenModeFlag.WriteOnly)
        canvas.save(buf, "PNG")
        buf.close()

        nsImage = NSImage.alloc().initWithData_(
            NSData.dataWithBytes_length_(data.data(), data.size())
        )
        tile = (NSApp or NSApplication.sharedApplication()).dockTile()
        if imageView is None:
            imageView = NSImageView.alloc().init()
            tile.setContentView_(imageView)
        imageView.setImage_(nsImage)
        tile.display()

    def restore() -> None:
        nonlocal imageView
        if imageView is None:
            return
        tile = (NSApp or NSApplication.sharedApplication()).dockTile()
        tile.setContentView_(None)
        tile.display()
        imageView = None

    def onSpeedChanged(speed: int) -> None:
        if not (cfg.shouldShowDockSpeed.value and cfg.shouldShowDockIcon.value):
            return
        if speed <= 0:
            restore()
            return
        render(f"{toReadableSize(speed)}/s")

    def onShowSpeedChanged(enabled: bool) -> None:
        if not enabled:
            restore()

    def onShowIconChanged(visible: bool) -> None:
        setDockIconVisible(visible, activate=True)
        restore()

    cfg.shouldShowDockIcon.valueChanged.connect(onShowIconChanged)
    speedMeter.speedChanged.connect(onSpeedChanged)
    cfg.shouldShowDockSpeed.valueChanged.connect(onShowSpeedChanged)
