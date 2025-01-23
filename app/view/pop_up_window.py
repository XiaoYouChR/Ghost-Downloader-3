from os.path import dirname, basename

from PySide6.QtCore import Qt, QUrl, QTimer, QEasingCurve, QPropertyAnimation, QRect, QFileInfo
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import QWidget, QFileIconProvider
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets.common.screen import getCurrentScreenGeometry
from qframelesswindow import WindowEffect

from app.common.methods import openFile, bringWindowToTop
from app.view.Ui_PopUpWindow import Ui_PopUpWindow


class PopUpWindow(QWidget, Ui_PopUpWindow):
    def __init__(self, fileResolvePath:str, mainWindow=None):
        super().__init__(parent=None)

        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus)

        # Acrylic Effect
        self.windowEffect = WindowEffect(self)
        self.windowEffect.setAcrylicEffect(self.winId())

        # 设置界面图标和文字
        self.setStyleSheet(
            """
            .QPushButton{
                background-color:transparent;
                border:none;
            }
            QLabel {
                font: 11pt;
                color: #5F5F5F;
            }
            """
        )
        self.closeBtn.setIcon(FIF.CLOSE.icon())
        self.mainWindowBtn.setIcon(FIF.HOME.icon())

        logoPixmap = QPixmap(":/image/logo_withoutBackground.png")

        self.logoLabel.setPixmap(logoPixmap)
        self.logoLabel.setFixedSize(16, 16)

        _ = QFileIconProvider().icon(QFileInfo(fileResolvePath)).pixmap(128, 128)  # 自动获取图标
        if _:
            self.fileIconLabel.setPixmap(_)
            self.fileIconLabel.setFixedSize(64, 64)

        else:
            self.fileIconLabel.setPixmap(logoPixmap)
            self.fileIconLabel.setFixedSize(64, 64)

        self.fileNameLabel.setText(basename(fileResolvePath))

        # Connect Signal To Slot
        self.closeBtn.clicked.connect(self.__moveOut)
        if mainWindow:
            self.mainWindowBtn.clicked.connect(lambda: bringWindowToTop(mainWindow))
        self.openFileBtn.clicked.connect(lambda: openFile(fileResolvePath))
        self.openPathBtn.clicked.connect(lambda: openFile(dirname(fileResolvePath)))
        self.screenGeometry = getCurrentScreenGeometry()
        self.move(self.screenGeometry.width(), self.screenGeometry.height() - self.height() - 13)
        self.show()

    
    def showEvent(self, event):
        self.raise_()
        QTimer.singleShot(50, self.__moveIn)
        self.closeTimer = QTimer()
        self.closeTimer.setSingleShot(True)
        self.closeTimer.timeout.connect(self.__moveOut)
        self.closeTimer.start(10000)
        super().showEvent(event)

    def __moveIn(self):
        # 设置音效
        self.soundEffect = QSoundEffect(self)
        self.soundEffect.setSource(QUrl.fromLocalFile(r":/res/completed.wav"))
        self.soundEffect.setVolume(100)
        self.soundEffect.play()
        # 动画
        self.geometryAnimation = QPropertyAnimation(self, b"geometry")
        self.geometryAnimation.setDuration(500)
        self.geometryAnimation.setStartValue(self.geometry())
        self.geometryAnimation.setEndValue(QRect(self.screenGeometry.width() - self.width() - 13, self.screenGeometry.height() - self.height() - 13, self.width(), self.height()))
        self.geometryAnimation.setEasingCurve(QEasingCurve.OutCubic)
        self.geometryAnimation.start()

    def __moveOut(self):
        self.geometryAnimation.setDuration(500)
        self.geometryAnimation.setStartValue(self.geometry())
        self.geometryAnimation.setEndValue(QRect(self.screenGeometry.width(), self.screenGeometry.height() - self.height() - 13, self.width(), self.height()))
        self.geometryAnimation.finished.connect(self.close)
        self.geometryAnimation.start()


    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragStartPosition = event.globalPosition().toPoint()
        super().mousePressEvent(event)


    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            deltaX = event.globalPosition().x() - self.dragStartPosition.x()
            maxX = self.screenGeometry.width() - self.width() - 13
            newX = maxX + deltaX
            if newX < maxX:
                newX = maxX
            self.move(newX, self.y())

        if hasattr(self, "closeTimer"):
            self.closeTimer.stop()

        super().mouseMoveEvent(event)


    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 拖动到超过阈值时松手后触发 self.__moveOut
            if self.pos().x() > (self.screenGeometry.width() - self.width() + 150):
                self.__moveOut()
            else:
                self.geometryAnimation.stop()
                self.geometryAnimation.setDuration(200)
                self.geometryAnimation.setStartValue(self.geometry())
                self.geometryAnimation.setEndValue(QRect(self.screenGeometry.width() - self.width() - 13, self.screenGeometry.height() - self.height() - 13, self.width(), self.height()))
                self.geometryAnimation.start()

        super().mouseReleaseEvent(event)
