import sys
from time import sleep

from PySide6.QtWidgets import QApplication

from app.view.pop_up_window import PopUpWindow

# noinspection PyUnresolvedReferences
import Res_rc

app = QApplication(sys.argv)

for i in range(10):
    PopUpWindow.showPopUpWindow(r"F:\Class-Widget\audio\attend_class.wav")

app.exec()
