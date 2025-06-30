import sys
import time

from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget
from desktop_notifier import DesktopNotifier


# noinspection PyUnresolvedReferences
import app.assets.Res_rc


class TestPopUpWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.notifier = DesktopNotifier()

        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        toast_receive_button = QPushButton("Show Toast Receive Button")
        # toast_receive_button.clicked.connect(self.runner.to_sync(self.show_received_toast))
        layout.addWidget(toast_receive_button)

        toast_finished_button = QPushButton("Show Toast Finished Button")
        # toast_finished_button.clicked.connect(self.runner.to_sync(self.show_finished_toast))
        layout.addWidget(toast_finished_button)

        self.setLayout(layout)

    async def show_received_toast(self):
        ...

    async def show_finished_toast(self):
        ...


if __name__ == "__main__":
    app = QApplication(sys.argv)
    test_window = TestPopUpWindow()
    test_window.show()
    app.exec()
