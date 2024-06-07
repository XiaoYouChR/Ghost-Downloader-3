# coding: utf-8
from pathlib import Path

import darkdetect
from PySide6.QtCore import QSize, QUrl, QThread, Signal, QTimer
from PySide6.QtGui import QIcon, QDesktopServices
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentIcon as FIF, isDarkTheme, setTheme, Theme
from qfluentwidgets import NavigationItemPosition, MessageBox, MSFluentWindow, SplashScreen, toggleTheme

from .home_interface import HomeInterface
from .task_interface import TaskInterface
from ..common.signal_bus import signalBus
from ..components.add_task_option_dialog import AddTaskOptionDialog

class ThemeChangedListener(QThread):
    themeChanged = Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        darkdetect.listener(self.themeChanged.emit)

class MainWindow(MSFluentWindow):

    def __init__(self):
        super().__init__()
        self.initWindow()

        # create sub interface
        self.homeInterface = HomeInterface(self)
        self.taskInterface = TaskInterface(self)
        # self.debugInterface = DebugInterface(self)

        # add items to navigation interface
        self.initNavigation()

        # 创建检测主题色更改线程
        self.themeChangedListener = ThemeChangedListener(self)
        self.themeChangedListener.themeChanged.connect(self.toggleTheme)
        self.themeChangedListener.start()

        # createUnfinishedTask
        historyFile = Path("./history")
        # 未完成任务记录文件格式示例: [{"url": "xxx", "fileName": "xxx", "filePath": "xxx", "blockNum": x}]
        if historyFile.exists():
            with open(historyFile, 'r', encoding='utf-8') as f:
                unfinishedTaskInfo = f.readlines()
                print(unfinishedTaskInfo)
                for i in unfinishedTaskInfo:
                    if i:  # 避免空行
                        i = eval(i)
                        signalBus.addTaskSignal.emit(i['url'], i['filePath'], i['blockNum'], i['fileName'], None, True)
        else:
            historyFile.touch()

        self.splashScreen.finish()

    def toggleTheme(self, callback: str):
        if callback == 'Dark':
            setTheme(Theme.DARK)
            QTimer.singleShot(100, lambda: self.windowEffect.setMicaEffect(self.winId(), True))
            QTimer.singleShot(200, lambda: self.windowEffect.setMicaEffect(self.winId(), True))
            QTimer.singleShot(300, lambda: self.windowEffect.setMicaEffect(self.winId(), True))

        elif callback == 'Light':
            setTheme(Theme.LIGHT)

    def initNavigation(self):
        # add navigation items
        self.addSubInterface(self.homeInterface, FIF.HOME, "主页")
        self.addSubInterface(self.taskInterface, FIF.DOWNLOAD, "任务列表")
        self.navigationInterface.addItem(
            routeKey='addTaskBtn',
            text='新建任务',
            selectable=False,
            icon=FIF.ADD,
            onClick=self.showAddTaskBox,
            position=NavigationItemPosition.TOP,
        )

        # self.addSubInterface(self.debugInterface, FIF.DEVELOPER_TOOLS, "调试信息")
        # add custom widget to bottom
        self.navigationInterface.addItem(
            routeKey='avatar',
            text='关于',
            selectable=False,
            icon=FIF.INFO,
            onClick=self.showInfoMessageBox,
            position=NavigationItemPosition.BOTTOM,
        )

    def initWindow(self):
        self.resize(960, 780)
        self.setWindowIcon(QIcon(':/icon/logo.png'))
        self.setWindowTitle('Ghost Downloader')

        # create splash screen
        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(QSize(106, 106))
        self.splashScreen.raise_()

        desktop = QApplication.screens()[0].availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)
        self.show()
        QApplication.processEvents()

    def showInfoMessageBox(self):
        w = MessageBox(
            '关于 Ghost Downloader',
            '当前版本 3.0.1\n程序作者 晓游ChR',
            self
        )
        w.yesButton.setText('了解作者')
        w.cancelButton.setText('关闭窗口')

        if w.exec():
            QDesktopServices.openUrl(QUrl('https://space.bilibili.com/437313511'))


    def showAddTaskBox(self):
        w = AddTaskOptionDialog(self)
        w.exec()

    def closeEvent(self, event):
        super().closeEvent(event)

        self.themeChangedListener.terminate()

        for i in self.taskInterface.cards:
            if i.paused:
                pass
            else:
                i.pauseTask()

        event.accept()
