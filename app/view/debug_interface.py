import sys
import time

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QVBoxLayout, QWidget, QFileDialog
from qfluentwidgets import TextEdit, PushButton


class DebugInterface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("DebugInterface")
        self.init_ui()

    def init_ui(self):
        self.text_browser = TextEdit(self)
        self.text_browser.setReadOnly(True)
        # self.button = PushButton("Print Hello World", self)
        # self.button.clicked.connect(self.print_hello_world)
        self.outputButton = PushButton("导出日志", self)
        self.outputButton.clicked.connect(self.output_log)

        layout = QVBoxLayout()
        layout.addWidget(self.text_browser)
        # layout.addWidget(self.button)
        layout.addWidget(self.outputButton)

        self.setLayout(layout)

        # 重定向标准输出流和错误流到自定义函数
        sys.stdout = self.CustomStdout(self.text_browser)
        sys.stderr = self.CustomStderr(self.text_browser)

    def output_log(self):
        saveFileName = QFileDialog.getSaveFileName(
            self, "选择导出路径", f"./导出日志-{int(time.time())}.log", "日志文件 (*.log)")[0]

        if not saveFileName:
            return
        else:
            with open(saveFileName, "w", encoding="utf-8") as f:
                f.write(self.text_browser.toPlainText())
                f.flush()
                f.close()

    # def print_hello_world(self):
    #     print("Hello World")
    #
    #     # 引发一个示例错误
    #     x = 1 / 0

    class CustomStdout:
        def __init__(self, text_browser):
            self.text_browser = text_browser

        def write(self, message):
            # 在控制台打印
            sys.__stdout__.write(message)
            sys.__stdout__.flush()

            # 在QTextEdit中显示
            cursor = self.text_browser.textCursor()
            cursor.movePosition(QTextCursor.End)
            cursor.insertText(message)
            self.text_browser.setTextCursor(cursor)
            self.text_browser.ensureCursorVisible()

    class CustomStderr:
        def __init__(self, text_browser):
            self.text_browser = text_browser

        def write(self, message):
            # 在控制台打印
            sys.__stderr__.write(message)
            sys.__stderr__.flush()

            # 在QTextEdit中显示
            cursor = self.text_browser.textCursor()
            cursor.movePosition(QTextCursor.End)
            cursor.insertText(message)
            self.text_browser.setTextCursor(cursor)
            self.text_browser.ensureCursorVisible()

    def closeEvent(self, event):
        # 恢复标准输出流和错误流
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        super().closeEvent(event)

# if __name__ == '__main__':
#     app = QApplication(sys.argv)
#     window = DebugInterface()
#     sys.exit(app.exec())
