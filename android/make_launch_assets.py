from pathlib import Path

from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter

REPO = Path(__file__).resolve().parent.parent
LOGO = REPO / "app" / "assets" / "logo.png"
GHOST = REPO / "app" / "assets" / "logo_withoutBackground.png"
OUT = REPO / "android" / "res"

GHOST_SCALE = 0.40

GRADIENT_TOP = QColor(201, 198, 226)
GRADIENT_BOTTOM = QColor(174, 205, 245)

def contentRect(image: QImage) -> QRect:
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
    cropped = ghost.copy(contentRect(ghost))
    target = int(size * GHOST_SCALE)
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

def saveSplashLogo() -> None:
    # 开屏(windowBackground)居中徽标。用 logo.png 而非裸幽灵: 裸幽灵是白的、浅色开屏底上隐形;
    # logo.png 自带圆角渐变底深浅都可见, 圆角外透明处由 layer-list 底色层透出(随 values-night 切)。
    logo = QImage(str(LOGO)).convertToFormat(QImage.Format.Format_ARGB32)
    scaled = logo.scaled(
        512, 512,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    scaled.save(str(OUT / "splash_logo.png"))

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    saveForegroundIcon()
    saveBackgroundIcon()
    saveSplashLogo()
    print(f"已生成: {', '.join(p.name for p in sorted(OUT.glob('*')))}")
