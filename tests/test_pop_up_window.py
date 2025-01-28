import sys
from time import sleep

from PySide6.QtWidgets import QApplication

from app.view.pop_up_window import FinishedPopUpWindow, ReceivedPopUpWindow

# noinspection PyUnresolvedReferences
import Res_rc

app = QApplication(sys.argv)

for i in range(10):
    ReceivedPopUpWindow.showPopUpWindow(f"")
    FinishedPopUpWindow.showPopUpWindow(r"F:\Class-Widget\audio\attend_class.wav")

app.exec()
