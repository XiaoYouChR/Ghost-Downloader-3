import sys

from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget

# noinspection PyUnresolvedReferences
import resources.Res_rc
from app.view.pop_up_window import FinishedPopUpWindow, ReceivedPopUpWindow


class TestPopUpWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        received_button = QPushButton("Show Received PopUp")
        received_button.clicked.connect(self.show_received_pop_up)
        layout.addWidget(received_button)

        finished_button = QPushButton("Show Finished PopUp")
        finished_button.clicked.connect(self.show_finished_pop_up)
        layout.addWidget(finished_button)

        toast_receive_button = QPushButton("Show Toast Receive Button")
        toast_receive_button.clicked.connect(self.show_received_toast)
        layout.addWidget(toast_receive_button)

        toast_finished_button = QPushButton("Show Toast Finished Button")
        toast_finished_button.clicked.connect(self.show_finished_toast)
        layout.addWidget(toast_finished_button)

        self.setLayout(layout)

    def show_received_toast(self):
        from app.common.concurrent.TaskExecutor import TaskExecutor
        from pathlib import Path
        from PySide6.QtCore import QStandardPaths, QResource
        from win11toast import toast

        logoTempFile = Path(QStandardPaths.writableLocation(QStandardPaths.TempLocation) + "/gd3_logo.png")
        if not logoTempFile.exists():
            with open(logoTempFile, "wb") as f:
                f.write(QResource(":/image/logo.png").data())
        icon = {
            'src': f"file://{logoTempFile}",
            'placement': 'appLogoOverride'
        }
        TaskExecutor.run(toast, "接收到来自浏览器的下载任务:", "https://cn.pornhub.com", on_click=lambda args: print('clicked!', args), icon=icon)

    def show_finished_toast(self):
        from app.common.concurrent.TaskExecutor import TaskExecutor
        from PySide6.QtCore import QStandardPaths, QFileInfo
        from win11toast import toast
        from PySide6.QtWidgets import QFileIconProvider
        from os.path import dirname

        fileResolovePath = r"C:\Users\BGTV\Downloads\Ghost-Downloader-v3.5.4-Windows-x86_64.zip"

        iconTempFile = QStandardPaths.writableLocation(QStandardPaths.TempLocation) + "/finished_file_icon.png"
        QFileIconProvider().icon(QFileInfo(fileResolovePath)).pixmap(128, 128).save(iconTempFile, "PNG")

        icon = {
            'src': f"file://{iconTempFile}",
            'placement': 'appLogoOverride'
        }

        buttons = [
            {'activationType': 'protocol', 'arguments': fileResolovePath, 'content': '打开文件'},
            {'activationType': 'protocol', 'arguments': dirname(fileResolovePath), 'content': '打开目录'}
        ]

        TaskExecutor.run(toast, "下载完成", fileResolovePath, icon=icon, buttons=buttons)


    def show_received_pop_up(self):
        ReceivedPopUpWindow.showPopUpWindow(f"")

    def show_finished_pop_up(self):
        FinishedPopUpWindow.showPopUpWindow(r"F:\Class-Widget\audio\attend_class.wav")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    test_window = TestPopUpWindow()
    test_window.show()
    app.exec()