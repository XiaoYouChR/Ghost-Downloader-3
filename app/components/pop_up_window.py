from os.path import dirname, basename

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QUrl
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget
from qfluentwidgets import FluentIcon as FIF

from app.common.methods import openFile
from app.components.Ui_PopUpWindow import Ui_PopUpWindow


class PopUpWindow(QWidget, Ui_PopUpWindow):
    def __init__(self, fileResolvePath:str, parent=None):
        super().__init__(parent)

        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose)
        # self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(Qt.FramelessWindowHint)

        # 设置音效
        self.soundEffect = QSoundEffect(self)
        self.soundEffect.setSource(QUrl(':/res/completed.wav'))
        self.soundEffect.play()

        # 设置界面图标和文字
        self.closeBtn.setIcon(FIF.CLOSE)
        self.showMainWindowBtn.setIcon(FIF.HOME)
        self.fileNameLabel.setText(basename(fileResolvePath))

        # Connect Signal To Slot
        self.closeBtn.clicked.connect(self.__fadeOut)
        # self.showMainWindowBtn.clicked.connect(bringWindowToTop(self.parent()))
        self.openFileBtn.clicked.connect(lambda: openFile(fileResolvePath))
        self.openPathBtn.clicked.connect(lambda: openFile(dirname(fileResolvePath)))

    # def paintEvent(self, event):
    #     painter = QPainter(self)
    #     painter.setRenderHint()
    #     painter.setPen(Qt.NoPen)
    #     painter.drawRoundedRect(self.rect(), 10, 10)

    def showEvent(self, e):
        """ fade in """
        opacityEffect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(opacityEffect)
        opacityAni = QPropertyAnimation(opacityEffect, b'opacity', self)
        opacityAni.setStartValue(0)
        opacityAni.setEndValue(1)
        opacityAni.setDuration(1000)
        opacityAni.setEasingCurve(QEasingCurve.InSine)
        opacityAni.finished.connect(lambda: self.setGraphicsEffect(None))
        opacityAni.start()
        super().showEvent(e)

    def __fadeOut(self):
        """ fade out """
        opacityEffect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(opacityEffect)
        opacityAni = QPropertyAnimation(opacityEffect, b'opacity', self)
        opacityAni.setStartValue(1)
        opacityAni.setEndValue(0)
        opacityAni.setDuration(1000)
        opacityAni.setEasingCurve(QEasingCurve.InSine)
        opacityAni.finished.connect(self.close)
        opacityAni.finished.connect(opacityAni.deleteLater)
        opacityAni.start()