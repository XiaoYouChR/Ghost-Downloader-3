from PySide6.QtCore import QSize, QRect
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget, QHBoxLayout
from qfluentwidgets import BodyLabel, FluentIconBase, drawIcon, ProgressBar

# 我是傻逼
# class DisabledRichTextEdit(TextEdit):
#     def __init__(self, parent=None):
#         super().__init__(parent)
#
#     def copy(self):
#         # 仅复制纯文本到剪贴板
#         clipboard = QApplication.clipboard()
#         clipboard.setText(self.toPlainText())  # 使用纯文本格式
#
#     def paste(self):
#         # 仅粘贴纯文本
#         clipboard = QApplication.clipboard()
#         text = clipboard.text().replace(" ", "")  # 获取纯文本内容并去除空格
#         self.insertPlainText(text)  # 使用 insertPlainText 插入纯文本
#
#     def keyPressEvent(self, event):
#         if event.modifiers() == Qt.ControlModifier:
#             if event.key() == Qt.Key_C:
#                 self.copy()
#                 event.accept()  # 阻止默认复制操作
#             elif event.key() == Qt.Key_V:
#                 self.paste()
#                 event.accept()  # 阻止默认粘贴操作
#             else:
#                 super().keyPressEvent(event)
#         else:
#             super().keyPressEvent(event)


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


class TaskProgressBar(QWidget):
    def __init__(self, blockNum: int, parent=None):
        super().__init__(parent)

        self.blockNum = blockNum
        self.progressBarList = []

        # Setup UI
        self.HBoxLayout = QHBoxLayout(self)
        self.HBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.HBoxLayout.setSpacing(0)
        self.setLayout(self.HBoxLayout)

        for i in range(self.blockNum):
            _ = ProgressBar(self)
            self.HBoxLayout.addWidget(_)
            self.progressBarList.append(_)

    def addProgressBar(self, content: list, quantity: int):

        for i in range(quantity):
            _ = ProgressBar(self)
            self.HBoxLayout.addWidget(_)
            self.progressBarList.append(_)

        self.blockNum += quantity

        for e, i in enumerate(content):  # 更改 Stretch
            self.HBoxLayout.setStretch(e, int((i["end"] - i["start"]) / 1048576))  # 除以1MB
