from pathlib import Path

from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter

REPO = Path(__file__).resolve().parent.parent
LOGO = REPO / "app" / "assets" / "logo.png"
GHOST = REPO / "app" / "assets" / "logo_withoutBackground.png"
OUT = REPO / "android" / "assets"

GHOST_RATIO = 0.40

GRADIENT_TOP = QColor(201, 198, 226)
GRADIENT_BOTTOM = QColor(174, 205, 245)

PRESPLASH_BG = QColor(243, 243, 243)

def _opaqueBounds(image: QImage) -> QRect:
    width, height = image.width(), image.height()
    minX, minY, maxX, maxY = width, height, 0, 0
    for y in range(height):
        for x in range(width):
            if (image.pixel(x, y) >> 24) & 0xFF > 128:
                minX, minY = min(minX, x), min(minY, y)
                maxX, maxY = max(maxX, x), max(maxY, y)
    return QRect(minX, minY, maxX - minX + 1, maxY - minY + 1)

def saveForegroundIcon() -> None:
    ghost = QImage(str(GHOST)).convertToFormat(QImage.Format.Format_ARGB32)
    size = ghost.width()
    cropped = ghost.copy(_opaqueBounds(ghost))
    target = int(size * GHOST_RATIO)
    scaled = cropped.scaled(
        target, target,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    canvas = QImage(size, size, QImage.Format.Format_ARGB32)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.drawImage((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
    painter.end()
    canvas.save(str(OUT / "icon_foreground.png"))

def saveBackgroundIcon() -> None:
    size = QImage(str(GHOST)).width()
    background = QImage(size, size, QImage.Format.Format_RGB888)
    gradient = QLinearGradient(QPointF(0, 0), QPointF(0, size))
    gradient.setColorAt(0.0, GRADIENT_TOP)
    gradient.setColorAt(1.0, GRADIENT_BOTTOM)
    painter = QPainter(background)
    painter.fillRect(background.rect(), gradient)
    painter.end()
    background.save(str(OUT / "icon_background.png"))

def savePresplashImage() -> None:
    logo = QImage(str(LOGO))
    canvas = QImage(1080, 1080, QImage.Format.Format_RGB888)
    canvas.fill(PRESPLASH_BG)
    logoSize = 520
    scaled = logo.scaled(
        logoSize, logoSize,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    painter = QPainter(canvas)
    painter.drawImage((1080 - scaled.width()) // 2, (1080 - scaled.height()) // 2, scaled)
    painter.end()
    canvas.save(str(OUT / "presplash.jpg"), "JPEG", 92)

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    saveForegroundIcon()
    saveBackgroundIcon()
    savePresplashImage()
    print(f"已生成: {', '.join(p.name for p in sorted(OUT.glob('*')))}")
