import sys
import time

from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget
from desktop_notifier import DesktopNotifier
from qt_async_threads import AbstractAsyncRunner, QtAsyncRunner


# noinspection PyUnresolvedReferences
import app.assets.Res_rc


class TestPopUpWindow(QWidget):
    def __init__(self, runner:AbstractAsyncRunner):
        super().__init__()
        self.runner = runner
        self.notifier = DesktopNotifier()

        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        toast_receive_button = QPushButton("Show Toast Receive Button")
        toast_receive_button.clicked.connect(self.runner.to_sync(self.show_received_toast))
        layout.addWidget(toast_receive_button)

        toast_finished_button = QPushButton("Show Toast Finished Button")
        toast_finished_button.clicked.connect(self.runner.to_sync(self.show_finished_toast))
        layout.addWidget(toast_finished_button)

        self.setLayout(layout)

    async def show_received_toast(self):
        await self.notifier.send("Received", "Received a message from server")

    async def show_finished_toast(self):
        ...


if __name__ == "__main__":
    app = QApplication(sys.argv)
    test_window = TestPopUpWindow(QtAsyncRunner())
    test_window.show()
    app.exec()
