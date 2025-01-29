import sys
from time import sleep

from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget

from app.view.pop_up_window import FinishedPopUpWindow, ReceivedPopUpWindow

# noinspection PyUnresolvedReferences
import Res_rc


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

        self.setLayout(layout)

    def show_received_pop_up(self):
        ReceivedPopUpWindow.showPopUpWindow(f"")

    def show_finished_pop_up(self):
        FinishedPopUpWindow.showPopUpWindow(r"F:\Class-Widget\audio\attend_class.wav")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    test_window = TestPopUpWindow()
    test_window.show()
    app.exec()