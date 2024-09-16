from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QPainter
from qfluentwidgets import FluentIconBase, drawIcon, BodyLabel


class IconBodyLabel(BodyLabel):
    def __init__(self, text:str, icon: FluentIconBase, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.icon = icon
        self.setContentsMargins(24, 0, 0, 0)  # 给 Icon 和 Text 之间留出 4px 的间距
        self.iconSize = QSize(16, 16)

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing |
                               QPainter.SmoothPixmapTransform)

        # 绘制图标
        iconHeight, iconWidth = self.iconSize.height(), self.iconSize.width()
        iconRect = QRect(4, (self.height() - iconHeight) // 2, iconWidth, iconHeight)
        drawIcon(self.icon, painter, iconRect)

# Test
# if __name__ == "__main__":
#     app = QApplication([])
#
#     setTheme(Theme.DARK, save=False)
#
#     window = IconBodyLabel("Sample Text", FluentIcon.WIFI, None)
#     window.show()
#
#     app.exec()
