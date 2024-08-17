# coding: utf-8
import ctypes
from pathlib import Path

import darkdetect
from PySide6.QtCore import QSize, QThread, Signal, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from loguru import logger
from qfluentwidgets import FluentIcon as FIF, setTheme, Theme
from qfluentwidgets import NavigationItemPosition, MSFluentWindow, SplashScreen
from win32comext.shell.shellcon import WM_USER

from .setting_interface import SettingInterface
from .task_interface import TaskInterface
from ..common.config import cfg
from ..common.custom_socket import GhostDownloaderSocketServer
from ..common.signal_bus import signalBus
from ..components.add_task_dialog import AddTaskOptionDialog
from ..components.custom_tray import CustomSystemTrayIcon


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
        self.taskInterface = TaskInterface(self)
        self.settingInterface = SettingInterface(self)
        # self.debugInterface = DebugInterface(self)

        # add items to navigation interface
        self.initNavigation()

        # 创建检测主题色更改线程
        self.themeChangedListener = ThemeChangedListener(self)
        self.themeChangedListener.themeChanged.connect(self.toggleTheme)
        self.themeChangedListener.start()

        # 创建未完成的任务
        historyFile = Path("{}/Ghost Downloader 记录文件".format(cfg.appPath))
        # 未完成任务记录文件格式示例: [{"url": "xxx", "fileName": "xxx", "filePath": "xxx", "blockNum": x, "status": "xxx"}]
        if historyFile.exists():
            with open(historyFile, 'r', encoding='utf-8') as f:
                unfinishedTaskInfo = f.readlines()
                logger.debug(f"Unfinished Task is following:{unfinishedTaskInfo}")
                for i in unfinishedTaskInfo:
                    if i:  # 避免空行
                        i = eval(i)
                        signalBus.addTaskSignal.emit(i['url'], i['filePath'], i['blockNum'], i['fileName'], i["status"], None, True)
        else:
            historyFile.touch()

        # 启动浏览器扩展服务器
        if cfg.enableBrowserExtension.value == True:
            self.browserExtensionSocket = GhostDownloaderSocketServer(self)
            self.browserExtensionSocket.receiveUrl.connect(self.addDownloadTaskFromWebSocket)

        # 创建托盘
        self.tray = CustomSystemTrayIcon(self)
        self.tray.show()

        self.splashScreen.finish()

    def addDownloadTaskFromWebSocket(self, url: str):
        self.taskInterface.addDownloadTask(url, cfg.downloadFolder.value, cfg.maxBlockNum.value)
        self.tray.showMessage(self.windowTitle(), f"已捕获来自浏览器的下载任务: \n{url}", self.windowIcon())

    def toggleTheme(self, callback: str):
        if callback == 'Dark':  # PySide6 特性，需要重试
            setTheme(Theme.DARK, save=False)
            QTimer.singleShot(100, lambda: self.windowEffect.setMicaEffect(self.winId(), True))
            QTimer.singleShot(200, lambda: self.windowEffect.setMicaEffect(self.winId(), True))
            QTimer.singleShot(300, lambda: self.windowEffect.setMicaEffect(self.winId(), True))

        elif callback == 'Light':
            setTheme(Theme.LIGHT, save=False)

    def initNavigation(self):
        # add navigation items
        self.addSubInterface(self.taskInterface, FIF.DOWNLOAD, "任务列表")
        self.navigationInterface.addItem(
            routeKey='addTaskButton',
            text='新建任务',
            selectable=False,
            icon=FIF.ADD,
            onClick=self.showAddTaskBox,
            position=NavigationItemPosition.TOP,
        )

        # self.addSubInterface(self.debugInterface, FIF.DEVELOPER_TOOLS, "调试信息")
        # add custom widget to bottom
        self.addSubInterface(self.settingInterface, FIF.SETTING, "设置", position=NavigationItemPosition.BOTTOM)

    def initWindow(self):
        self.resize(960, 780)
        self.setWindowIcon(QIcon(':/image/logo.png'))
        self.setWindowTitle('Ghost Downloader')

        # create splash screen
        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(QSize(106, 106))
        self.splashScreen.raise_()

        desktop = QApplication.screens()[0].availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w//2 - self.width()//2, h//2 - self.height()//2)
        self.show()
        QApplication.processEvents()


    def showAddTaskBox(self):
        w = AddTaskOptionDialog(self)
        w.exec()

    def closeEvent(self, event):
        # 拦截关闭事件，隐藏窗口而不是退出
        event.ignore()
        self.hide()

    def nativeEvent(self, eventType, message):
        # 处理窗口重复打开事件
        if eventType == "windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(message.__int__())

            if msg.message == WM_USER + 1:
                self.show()
                return True, 0

        return super().nativeEvent(eventType, message)