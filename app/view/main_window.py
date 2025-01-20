# coding: utf-8
import ctypes
import pickle
import sys
from ctypes import byref, c_int
from pathlib import Path

import darkdetect
from PySide6.QtCore import QSize, QThread, Signal, QTimer, QPropertyAnimation, QUrl, Slot, SignalInstance
from PySide6.QtGui import QIcon, QDragEnterEvent, QDropEvent, QKeySequence
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect
from loguru import logger
from qfluentwidgets import FluentIcon as FIF, setTheme, Theme
from qfluentwidgets import NavigationItemPosition, MSFluentWindow, SplashScreen

from .setting_interface import SettingInterface
from .task_interface import TaskInterface
from ..common.config import cfg
from ..common.custom_socket import GhostDownloaderSocketServer
from ..common.signal_bus import signalBus
from ..components.add_task_dialog import AddTaskOptionDialog
from ..components.custom_tray import CustomSystemTrayIcon
from ..components.update_dialog import checkUpdate


class CustomSplashScreen(SplashScreen):

    def finish(self):
        """ fade out splash screen """
        opacityEffect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(opacityEffect)
        opacityAni = QPropertyAnimation(opacityEffect, b'opacity', self)
        opacityAni.setStartValue(1)
        opacityAni.setEndValue(0)
        opacityAni.setDuration(200)
        opacityAni.finished.connect(self.deleteLater)
        opacityAni.start()


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

        # 设置背景特效
        self.applyBackgroundEffectByCfg()

        # 创建检测主题色更改线程
        self.themeChangedListener = ThemeChangedListener(self)
        self.themeChangedListener.themeChanged.connect(self.toggleTheme)
        self.themeChangedListener.start()

        # 创建未完成的任务
        historyFile = Path("{}/Ghost Downloader 记录文件".format(cfg.appPath))
        if historyFile.exists():
            with open(historyFile, 'rb') as f:
                try:
                    while True:
                        taskRecord = pickle.load(f)
                        logger.debug(f"Unfinished Task is following: {taskRecord}")
                        signalBus.addTaskSignal.emit(taskRecord['url'], taskRecord['filePath'], taskRecord['blockNum'], taskRecord['fileName'], taskRecord['status'], taskRecord['headers'], True)
                except EOFError:
                    pass
        else:
            historyFile.touch()

        # 启动浏览器扩展服务器
        self.browserExtensionServer = None

        if cfg.enableBrowserExtension.value == True:
            self.runBrowserExtensionServer()

        # 创建托盘
        self.tray = CustomSystemTrayIcon(self)
        self.tray.show()

        # 检查更新
        if cfg.checkUpdateAtStartUp.value == True:
            checkUpdate(self)

        self.splashScreen.finish()
        self.dropTimmer = QTimer()
        self.dropTimmer.timeout.connect(self._showAddTaskBox)

    def runBrowserExtensionServer(self):
        if not self.browserExtensionServer:
            self.browserExtensionServer = GhostDownloaderSocketServer(self)
            self.browserExtensionServer.receiveUrl.connect(self.__addDownloadTaskFromWebSocket)

    def stopBrowserExtensionServer(self):
        self.browserExtensionServer.server.close()
        self.browserExtensionServer.server.deleteLater()
        self.browserExtensionServer.deleteLater()

        self.browserExtensionServer = None

    def __addDownloadTaskFromWebSocket(self, url: str, headers: dict):
        signalBus.addTaskSignal.emit(url, cfg.downloadFolder.value, cfg.maxBlockNum.value, None, "working", headers, None)
        self.tray.showMessage(self.windowTitle(), f"已捕获来自浏览器的下载任务: \n{url}", self.windowIcon())

    def toggleTheme(self, callback: str):
        if callback == 'Dark':  # PySide6 特性，需要重试
            setTheme(Theme.DARK, save=False)
            if cfg.backgroundEffect.value in ['Mica', 'MicaBlur', 'MicaAlt']:
                QTimer.singleShot(100, self.applyBackgroundEffectByCfg)
                QTimer.singleShot(200, self.applyBackgroundEffectByCfg)
                QTimer.singleShot(300, self.applyBackgroundEffectByCfg)

        elif callback == 'Light':
            setTheme(Theme.LIGHT, save=False)

        self.applyBackgroundEffectByCfg()

    def applyBackgroundEffectByCfg(self):  # 不应设置 _isMicaEnabled 的值
        if sys.platform == 'win32':
            self.windowEffect.removeBackgroundEffect(self.winId())

            if cfg.backgroundEffect.value == 'Acrylic':
                self.windowEffect.setAcrylicEffect(self.winId(), "00000030" if darkdetect.isDark() else "F2F2F230")
            elif cfg.backgroundEffect.value == 'Mica':
                self.windowEffect.setMicaEffect(self.winId(), darkdetect.isDark())
            elif cfg.backgroundEffect.value == 'MicaBlur':
                self.windowEffect.setMicaEffect(self.winId(), darkdetect.isDark())
                self.windowEffect.DwmSetWindowAttribute(self.winId(), 38, byref(c_int(3)), 4)
            elif cfg.backgroundEffect.value == 'MicaAlt':
                self.windowEffect.setMicaEffect(self.winId(), darkdetect.isDark(), True)
            elif cfg.backgroundEffect.value == 'Aero':
                self.windowEffect.setAeroEffect(self.winId())


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

        if cfg.geometry.value == "Default":
            self.resize(960, 780)
            desktop = QApplication.screens()[0].availableGeometry()
            w, h = desktop.width(), desktop.height()
            self.move(w//2 - self.width()//2, h//2 - self.height()//2)
        else:
            try:
                self.setGeometry(cfg.get(cfg.geometry))
            except Exception as e:
                logger.error(f"Failed to restore geometry: {e}")
                cfg.set(cfg.geometry, "Default")

                self.resize(960, 780)
                desktop = QApplication.screens()[0].availableGeometry()
                w, h = desktop.width(), desktop.height()
                self.move(w//2 - self.width()//2, h//2 - self.height()//2)

        self.setWindowIcon(QIcon(':/image/logo.png'))
        self.setWindowTitle('Ghost Downloader')

        # create splash screen
        self.splashScreen = CustomSplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(QSize(106, 106))
        self.splashScreen.raise_()

        self.show()

        QApplication.processEvents()

    def showAddTaskBox(self):
        w = AddTaskOptionDialog(self)
        w.exec()

    def _showAddTaskBox(self):
        text = self.urlsText
        w = AddTaskOptionDialog(self)
        w.linkTextEdit.setText(text)
        w.exec()
        self.dropTimmer.stop()

    def closeEvent(self, event):
        # 拦截关闭事件，隐藏窗口而不是退出
        event.ignore()
        # 保存窗口位置
        cfg.set(cfg.geometry, self.geometry())

        self.hide()

    def nativeEvent(self, eventType, message):
        # 处理窗口重复打开事件
        if eventType == "windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(message.__int__())

            # WIN_USER = 1024
            if msg.message == 1024 + 1:
                self.show()
                return True, 0

        return super().nativeEvent(eventType, message)

    def dragEnterEvent(self, event: QDragEnterEvent):
        logger.debug(f'Get event: {event}')
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def __setUrlsAndShowAddTaskBox(self, text):
        self.urlsText = text
        self.dropTimmer.start(1000)

    def dropEvent(self, event: QDropEvent):
        mime = event.mimeData()
        if mime.hasUrls():
            urls = mime.urls()
            text = '\n'.join([url.toString() for url in urls])
        elif mime.hasText():
            text = mime.text()
        else:
            return
        self.__setUrlsAndShowAddTaskBox(text)
        event.accept()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Paste):
            text = QApplication.clipboard().text()
            self.__setUrlsAndShowAddTaskBox(text)
        else:
            super().keyPressEvent(event)


# https://github.com/XiaoYouChR/Ghost-Downloader-3