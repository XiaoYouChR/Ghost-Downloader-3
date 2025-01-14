from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from qfluentwidgets import TextEdit


class DisabledRichTextEdit(TextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)

    def copy(self):
        # 仅复制纯文本到剪贴板
        clipboard = QApplication.clipboard()
        clipboard.setText(self.toPlainText())  # 使用纯文本格式

    def paste(self):
        # 仅粘贴纯文本
        clipboard = QApplication.clipboard()
        text = clipboard.text().replace(" ", "")  # 获取纯文本内容并去除空格
        self.insertPlainText(text)  # 使用 insertPlainText 插入纯文本

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.ControlModifier:
            if event.key() == Qt.Key_C:
                self.copy()
                event.accept()  # 阻止默认复制操作
            elif event.key() == Qt.Key_V:
                self.paste()
                event.accept()  # 阻止默认粘贴操作
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)
