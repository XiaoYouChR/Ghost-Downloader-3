import sys
from os.path import dirname
from pathlib import Path

from PySide6.QtCore import QStandardPaths, QFileInfo, QTimer, QResource, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget, QFileIconProvider
from desktop_notifier import DesktopNotifierSync, Icon, Button

# noinspection PyUnresolvedReferences
import resources.Res_rc


def openFile(fileResolve):
    """
    打开文件

    :param fileResolve: 文件路径
    """
    QDesktopServices.openUrl(QUrl.fromLocalFile(fileResolve))

_ = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation) + "/gd3_logo.png")
if not _.exists():
    with open(_, "wb") as f:
        f.write(QResource(":/image/logo.png").data())

desktopNotifierIcon = Icon(path=_)
desktopNotifier = DesktopNotifierSync(app_name="Ghost Downloader", app_icon=desktopNotifierIcon)

class LimitedRunTimer(QTimer):
    """
    一个在运行指定次数后会自动销毁的 QTimer。
    """

    _activeTimers = set()   # 防止垃圾回收

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback
        self._runCount = 0
        self.maxRuns = 50  # 总运行次数

        self.setInterval(200)  # 设置时间间隔为 200ms
        self.timeout.connect(self._onTimeout)

    def _onTimeout(self):
        """计时器每次超时时调用的内部槽函数。"""
        self._runCount += 1

        # 执行回调函数
        if self._callback:
            try:
                self._callback()
            except Exception:
                self.stopAndDestroy()
                return

        if self._runCount >= self.maxRuns:
            self.stopAndDestroy()

    def stopAndDestroy(self):
        self.stop()
        LimitedRunTimer._activeTimers.discard(self)
        self.deleteLater()

    @staticmethod
    def create(callback):
        timerInstance = LimitedRunTimer(callback)
        LimitedRunTimer._activeTimers.add(timerInstance) # 将实例添加到集合中，以保证其存活
        timerInstance.start()
        return timerInstance


class TestPopUpWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        received_button = QPushButton("Show Received PopUp")
        received_button.clicked.connect(self.show_received_pop_up)
        layout.addWidget(received_button)

        self.setLayout(layout)

    def show_received_pop_up(self):
        fileResolvePath = r"C:\Users\XiaoYouChR\Downloads\OfficeSetup.exe"

        iconTempFile = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.TempLocation) + "/finished_file_icon.png"
        QFileIconProvider().icon(QFileInfo(fileResolvePath)).pixmap(48, 48).scaled(128, 128,
                                                                                   aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
                                                                                   mode=Qt.TransformationMode.SmoothTransformation).save(iconTempFile, "PNG")

        buttons = [Button(('打开文件'), lambda: openFile(fileResolvePath)), Button(('打开目录'), lambda: openFile(dirname(fileResolvePath)))]

        LimitedRunTimer.create(desktopNotifier.get_current_notifications)

        return desktopNotifier.send("下载完成", fileResolvePath, buttons=buttons,
                                    on_clicked=lambda: print("PopUpClicked"), icon=Icon(Path(iconTempFile)), timeout=10)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    test_window = TestPopUpWindow()
    test_window.show()
    app.exec()