import sys

from PySide6.QtWidgets import QApplication

from app.view.pop_up_window import PopUpWindow

import Res_rc

app = QApplication(sys.argv)

popUp = PopUpWindow(r"F:\Class-Widget\audio\attend_class.wav")

app.exec()