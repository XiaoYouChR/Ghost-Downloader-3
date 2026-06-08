"""从 logo.png 派生 Android adaptive icon(前景+背景两层)与 presplash。

拆两层是因为直接喂满幅圆角 logo, 启动器会把透明圆角填白 → ColorOS/MIUI 桌面图标外圈白边;
背景层满幅不透明渐变填掉圆角即消白边。改 logo.png 后重跑:
`QT_QPA_PLATFORM=offscreen python android/make_launch_assets.py`
"""

from pathlib import Path

from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter

REPO = Path(__file__).resolve().parent.parent
LOGO = REPO / "app" / "assets" / "logo.png"
GHOST = REPO / "app" / "assets" / "logo_withoutBackground.png"  # 幽灵主体, 透明背景
OUT = REPO / "android" / "assets"

# 幽灵内容占前景画布(108dp)比例。adaptive icon 只显示中心 72dp 视口(放大 1.5×), 故 0.40 桌面呈现约 0.60。
GHOST_RATIO = 0.40

# 背景渐变取自 logo 上/下边缘(竖向), 使圆角处透出的背景与 logo 自身渐变同色。
GRADIENT_TOP = QColor(201, 198, 226)
GRADIENT_BOTTOM = QColor(174, 205, 245)
# presplash 底色取浅色主窗背景, 冷启动到主窗无跳色。
PRESPLASH_BG = QColor(243, 243, 243)


def _alphaBounds(image: QImage) -> QRect:
    """幽灵实心像素的包围盒。阈值取 128 而非低值：源图实心幽灵两侧有不对称的微透明柔边,
    低阈值会把柔边算进 bbox 致中心偏移, 居中后实心主体反而偏向一侧(MIUI/ColorOS 上肉眼可见偏右)。"""
    width, height = image.width(), image.height()
    minX, minY, maxX, maxY = width, height, 0, 0
    for y in range(height):
        for x in range(width):
            if (image.pixel(x, y) >> 24) & 0xFF > 128:
                minX, minY = min(minX, x), min(minY, y)
                maxX, maxY = max(maxX, x), max(maxY, y)
    return QRect(minX, minY, maxX - minX + 1, maxY - minY + 1)


def writeForeground() -> None:
    # 前景=裁紧的幽灵主体居中缩放: 先裁到不透明边界去源留白, 再按 GHOST_RATIO 缩放, 四周留足安全区。
    ghost = QImage(str(GHOST)).convertToFormat(QImage.Format.Format_ARGB32)
    size = ghost.width()
    cropped = ghost.copy(_alphaBounds(ghost))
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


def writeBackground() -> None:
    # 背景=与 logo 同色的满幅竖向渐变, 满幅不透明以消圆角白边。
    size = QImage(str(GHOST)).width()
    background = QImage(size, size, QImage.Format.Format_RGB888)
    gradient = QLinearGradient(QPointF(0, 0), QPointF(0, size))
    gradient.setColorAt(0.0, GRADIENT_TOP)
    gradient.setColorAt(1.0, GRADIENT_BOTTOM)
    painter = QPainter(background)
    painter.fillRect(background.rect(), gradient)
    painter.end()
    background.save(str(OUT / "icon_background.png"))


def writePresplash() -> None:
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
    writeForeground()
    writeBackground()
    writePresplash()
    print(f"已生成: {', '.join(p.name for p in sorted(OUT.glob('*')))}")
