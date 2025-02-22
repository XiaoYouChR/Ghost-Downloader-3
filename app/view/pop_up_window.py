from os.path import dirname, basename

from PySide6.QtCore import Qt, QUrl, QTimer, QEasingCurve, QPropertyAnimation, QRect, QFileInfo, QObject, \
    QCoreApplication
from PySide6.QtGui import QPixmap, QPainter, QColor, QPainterPath
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import QWidget, QFileIconProvider, QPushButton, QToolButton
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets.common.screen import getCurrentScreenGeometry
from qframelesswindow import WindowEffect

from app.common.methods import openFile, bringWindowToTop
from app.view.Ui_PopUpWindow import Ui_PopUpWindow


class PopUpWindowBase(QWidget, Ui_PopUpWindow):
    def __init__(self, mainWindow=None):
        super().__init__(parent=None)

        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus)

        # Acrylic Effect
        self.windowEffect = WindowEffect(self)
        self.windowEffect.setAcrylicEffect(self.winId(), "FFFFFF30")

        # 初始化 globalPath, 用于解决鼠标穿透
        self.globalPath = QPainterPath()
        self.globalPath.lineTo(self.width(), 0)
        self.globalPath.lineTo(self.width(), self.height())
        self.globalPath.lineTo(0, self.height())
        self.globalPath.lineTo(0, 0)

        self.geometryAnimation = QPropertyAnimation(self, b"geometry")

        # 设置界面图标和文字
        self.setStyleSheet(
            """
            .QToolButton{
                background-color:transparent;
                border:none;
            }
            QLabel#contentLabel, QLabel#captionLabel {
                font: 12pt;
                color: #4F4F4F;
            }
            QLabel#titleLabel {
                font: 11pt;
                color: black;
            }
            .QPushButton {
                background: rgba(255, 255, 255, 0.3605);
                border: 1px solid rgba(255, 255, 255, 0.053);
                border-top: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 5px;
                color: black;
                font: 14px 'Segoe UI', 'Microsoft YaHei', 'PingFang SC';
                padding: 5px 12px 6px 12px;
                outline: none;
            }
            
            .QPushButton:hover{
                background: rgba(255, 255, 255, 0.3837);
            }
            
            .QPushButton:pressed {
                color: rgba(0, 0, 0, 0.786);
                background: rgba(255, 255, 255, 0.3326);
                border-top: 1px solid rgba(255, 255, 255, 0.053);
            }          
            """
        )
        self.closeBtn.setIcon(FIF.CLOSE.icon())

        # 主窗口按钮
        if mainWindow:
            self.mainWindowBtn = QToolButton(self)
            self.mainWindowBtn.setObjectName(u"mainWindowBtn")
            self.mainWindowBtn.setGeometry(QRect(280, 13, 24, 24))
            self.mainWindowBtn.setIcon(FIF.HOME.icon())
            self.mainWindowBtn.clicked.connect(lambda: bringWindowToTop(mainWindow))

        self.logoPixmap = QPixmap(":/image/logo_withoutBackground.png")
        self.logoLabel.setPixmap(self.logoPixmap)
        self.logoLabel.setFixedSize(16, 16)

        # Connect Signal To Slot
        self.closeBtn.clicked.connect(self.__moveOut)

        self.screenGeometry = getCurrentScreenGeometry()
        self.move(self.screenGeometry.width(), self.screenGeometry.height() - self.height() - 13)
        self.__manager = PopUpWindowManager()
        self.__manager.add(self)

    def paintEvent(self, e):
        # 解决鼠标穿透问题
        paint = QPainter(self)
        paint.setPen(Qt.transparent)
        paint.setBrush(QColor(0, 0, 0, 1))
        paint.drawPath(self.globalPath)
        super().paintEvent(e)


    def showEvent(self, event):
        self.raise_()
        QTimer.singleShot(50, self.__moveIn)
        self.closeTimer = QTimer()
        self.closeTimer.setSingleShot(True)
        self.closeTimer.timeout.connect(self.__moveOut)
        self.closeTimer.start(10000)
        super().showEvent(event)


    def _playSound(self):
        # 设置音效
        self.soundEffect = QSoundEffect(self)
        self.soundEffect.setSource(QUrl.fromLocalFile(r":/res/completed_task.wav"))
        self.soundEffect.setVolume(100)
        self.soundEffect.play()


    def __moveIn(self):
        self._playSound()

        if not hasattr(self, "geometryAnimation"):
            self.geometryAnimation = QPropertyAnimation(self, b"geometry")

        # 动画
        self.geometryAnimation.setDuration(500)
        self.geometryAnimation.setStartValue(self.geometry())
        self.geometryAnimation.setEndValue(QRect(self.screenGeometry.width() - self.width() - 13, self.y(), self.width(), self.height()))
        self.geometryAnimation.setEasingCurve(QEasingCurve.OutCubic)
        self.geometryAnimation.start()


    def __moveOut(self):
        try:
            if not hasattr(self, "geometryAnimation"):
                self.geometryAnimation = QPropertyAnimation(self, b"geometry")

            self.geometryAnimation.setDuration(500)
            self.geometryAnimation.setStartValue(self.geometry())
            self.geometryAnimation.setEndValue(QRect(self.screenGeometry.width(), self.y(), self.width(), self.height()))
            self.geometryAnimation.finished.connect(self.close)
            self.geometryAnimation.start()
        except RuntimeError:  # 防止多次点击导致的错误
            pass
        except Exception as e:
            raise e


    def closeEvent(self, event):
        self.__manager.remove(self)
        super().closeEvent(event)


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
                self.geometryAnimation.setEndValue(QRect(self.screenGeometry.width() - self.width() - 13, self.y(), self.width(), self.height()))
                self.geometryAnimation.start()

        super().mouseReleaseEvent(event)


    @classmethod
    def showPopUpWindow(cls, mainWindow=None):
        return cls(mainWindow)


class FinishedPopUpWindow(PopUpWindowBase):
    def __init__(self, fileResolvePath: str, mainWindow=None):
        super().__init__(mainWindow)

        self.contentLabel.setGeometry(QRect(90, 60, 261, 20))
        self.contentLabel.setWordWrap(False)

        self.openPathBtn = QPushButton(self)
        self.openPathBtn.setObjectName(u"openPathBtn")
        self.openPathBtn.setGeometry(QRect(90, 82, 125, 28))
        self.openFileBtn = QPushButton(self)
        self.openFileBtn.setObjectName(u"openFileBtn")
        self.openFileBtn.setGeometry(QRect(223, 82, 125, 28))

        self.captionLabel.setText(QCoreApplication.translate("PopUpWindow", u"\u4e0b\u8f7d\u5b8c\u6210：", None))
        self.openPathBtn.setText(QCoreApplication.translate("PopUpWindow", u"\u6253\u5f00\u76ee\u5f55", None))
        self.openFileBtn.setText(QCoreApplication.translate("PopUpWindow", u"\u6253\u5f00\u6587\u4ef6", None))

        _ = QFileIconProvider().icon(QFileInfo(fileResolvePath)).pixmap(128, 128)  # 自动获取图标
        if _:
            self.contentIconLabel.setPixmap(_)
            self.contentIconLabel.setFixedSize(64, 64)

        else:
            self.contentIconLabel.setPixmap(self.logoPixmap)
            self.contentIconLabel.setFixedSize(64, 64)

        _ = basename(fileResolvePath)
        self.contentLabel.setText(_)
        self.contentLabel.fontMetrics().elidedText(_, Qt.ElideRight, 261)
        
        self.openFileBtn.clicked.connect(lambda: openFile(fileResolvePath))
        self.openPathBtn.clicked.connect(lambda: openFile(dirname(fileResolvePath)))

        self.show()

    @classmethod
    def showPopUpWindow(cls, fileResolvePath:str, mainWindow=None):
        return cls(fileResolvePath, mainWindow)


class ReceivedPopUpWindow(PopUpWindowBase):
    def __init__(self, receiveContent:str, mainWindow=None):
        super().__init__(mainWindow)

        self.contentIconLabel.setPixmap(QPixmap(":/image/logo.png"))
        self.contentIconLabel.setFixedSize(64, 64)
        self.captionLabel.setText("接收到来自浏览器的下载任务:")
        self.contentLabel.setText(receiveContent)

        self.show()

    def _playSound(self):
        # 设置音效
        self.soundEffect = QSoundEffect(self)
        self.soundEffect.setSource(QUrl.fromLocalFile(r":/res/received_info.wav"))
        self.soundEffect.setVolume(100)
        self.soundEffect.play()

    @classmethod
    def showPopUpWindow(cls, receiveContent:str, mainWindow=None):
        return cls(receiveContent, mainWindow)


class PopUpWindowManager(QObject):
    """当多个 PopUpWindow 同时出现时，使用 PopUpWindowManager 来管理它们"""

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if PopUpWindowManager._initialized:
            return
        super().__init__()
        self.popUpWindows = []  # 强引用列表
        PopUpWindowManager._initialized = True

    def add(self, popUpWindow: PopUpWindowBase):
        # print("PopUpWindow Added")
        if popUpWindow not in self.popUpWindows:
            self.popUpWindows.append(popUpWindow)
            # 按照 PopUpWindow 的数量移动 PopUpWindow 的 y 坐标
            if len(self.popUpWindows) > 1:
                for i, popUp in enumerate(self.popUpWindows):
                    popUp.move(popUp.x(), getCurrentScreenGeometry().height() - ((popUp.height() + 13) * (len(self.popUpWindows) - i)))

    def remove(self, popUpWindow: PopUpWindowBase):
        # print("PopUpWindow Destroyed")
        if popUpWindow in self.popUpWindows:
            self.popUpWindows.remove(popUpWindow)
            # 按照 PopUpWindow 的数量移动 PopUpWindow 的 y 坐标
            for i, popUp in enumerate(self.popUpWindows):
                popUp.move(popUp.x(), getCurrentScreenGeometry().height() - ((popUp.height() + 13) * (len(self.popUpWindows) - i)))
