from PySide6.QtCore import QBuffer, QByteArray, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPainterPath, QPen, QPixmap

from AppKit import (
    NSApp, NSApplication, NSImage, NSImageView, NSProgressIndicator, NSView,
    NSApplicationActivationPolicyRegular, NSApplicationActivationPolicyAccessory,
)
from Foundation import NSData

from app.config.cfg import cfg
from app.format import toDockSpeed
from app.services.speed_meter import speedMeter


def setDockIconVisible(visible: bool, activate: bool) -> None:
    app = NSApp or NSApplication.sharedApplication()
    app.setActivationPolicy_(
        NSApplicationActivationPolicyRegular if visible else NSApplicationActivationPolicyAccessory
    )
    if activate:
        app.activateIgnoringOtherApps_(True)


def setupDock() -> None:
    from app.services.task_service import taskService

    baseIcon = None
    container = None
    imageView = None
    progressBar = None

    def update(text: str, progress: float) -> None:
        nonlocal baseIcon, container, imageView, progressBar

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

        font = painter.font()
        font.setBold(True)
        pixel = int(size * 0.14)
        font.setPixelSize(pixel)
        maxWidth = size * 0.85
        while QFontMetricsF(font).horizontalAdvance(text) > maxWidth and pixel > 6:
            pixel -= 1
            font.setPixelSize(pixel)

        fm = QFontMetricsF(font)
        textX = (size - fm.horizontalAdvance(text)) / 2
        textY = size * 0.82

        path = QPainterPath()
        path.addText(textX, textY, font, text)
        painter.strokePath(
            path,
            QPen(QColor(0, 0, 0, 180), 12,
                 Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin),
        )
        painter.fillPath(path, QColor(255, 255, 255))
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
        if container is None:
            tileSize = tile.size()
            container = NSView.alloc().initWithFrame_(
                ((0, 0), (tileSize.width, tileSize.height))
            )
            imageView = NSImageView.alloc().initWithFrame_(
                ((0, 0), (tileSize.width, tileSize.height))
            )
            container.addSubview_(imageView)

            barHeight = tileSize.height * 0.08
            progressBar = NSProgressIndicator.alloc().initWithFrame_(
                ((0, 0), (tileSize.width, barHeight))
            )
            progressBar.setStyle_(0)
            progressBar.setMinValue_(0)
            progressBar.setMaxValue_(100)
            progressBar.setIndeterminate_(False)
            container.addSubview_(progressBar)

            tile.setContentView_(container)

        imageView.setImage_(nsImage)

        if progress >= 0:
            progressBar.setHidden_(False)
            progressBar.setDoubleValue_(progress)
        else:
            progressBar.setHidden_(True)

        tile.display()

    def clear() -> None:
        nonlocal container, imageView, progressBar
        if container is None:
            return
        tile = (NSApp or NSApplication.sharedApplication()).dockTile()
        tile.setContentView_(None)
        tile.display()
        container = None
        imageView = None
        progressBar = None

    def onSpeedChanged(speed: int) -> None:
        if not (cfg.shouldShowDockSpeed.value and cfg.shouldShowDockIcon.value):
            return
        if speed <= 0:
            clear()
            return
        update(toDockSpeed(speed, int(cfg.speedUnit.value)), taskService.runningProgress())

    def onShowSpeedChanged(enabled: bool) -> None:
        if not enabled:
            clear()

    def onShowIconChanged(visible: bool) -> None:
        setDockIconVisible(visible, activate=True)
        clear()

    cfg.shouldShowDockIcon.valueChanged.connect(onShowIconChanged)
    speedMeter.speedChanged.connect(onSpeedChanged)
    cfg.shouldShowDockSpeed.valueChanged.connect(onShowSpeedChanged)
