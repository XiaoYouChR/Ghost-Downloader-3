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
        pass
        # TaskExecutor.run(desktopNotifier.send, "Received:", "https://github.com", buttons=[
        #     Button("OpenFile", lambda :openFile(r"C:\Users\XiaoYouChR\Downloads\10.0 Cheetah & 10.1 Puma.png"))
        # ],)

    def show_finished_toast(self):
        pass
        # TaskExecutor.run(desktopNotifier.send, "Received:", "https://github.com", buttons=[
        #     Button("OpenFile", lambda :openFile(r"C:\Users\XiaoYouChR\Downloads\10.0 Cheetah & 10.1 Puma.png"))
        # ])

    def show_received_pop_up(self):
        ReceivedPopUpWindow.showPopUpWindow(f"")

    def show_finished_pop_up(self):
        FinishedPopUpWindow.showPopUpWindow(r"C:\Users\XiaoYouChR\Downloads\OfficeSetup.exe")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    test_window = TestPopUpWindow()
    test_window.show()
    app.exec()