# coding: utf-8
import ctypes
import pickle
import sys
from pathlib import Path

import darkdetect
from PySide6.QtCore import QSize, QThread, Signal, QTimer, QPropertyAnimation, QRect, QUrl
from PySide6.QtGui import QIcon, QDragEnterEvent, QDropEvent, QKeySequence, QDesktopServices, QColor, Qt
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect
from loguru import logger
from qfluentwidgets import FluentIcon as FIF, setTheme, Theme, isDarkTheme
from qfluentwidgets import NavigationItemPosition, MSFluentWindow, SplashScreen

from .setting_interface import SettingInterface
from .task_interface import TaskInterface
from ..common.config import cfg, Headers, attachmentTypes, FEEDBACK_URL
from ..common.custom_socket import GhostDownloaderSocketServer
from ..common.methods import getLinkInfo, bringWindowToTop, addDownloadTask, showMessageBox, \
    isGreaterEqualWin10, isLessThanWin10, isGreaterEqualWin11
from ..common.signal_bus import signalBus
from ..components.add_task_dialog import AddTaskOptionDialog
from ..components.custom_tray import CustomSystemTrayIcon
from ..components.update_dialog import checkUpdate


def updateFrameless(self):
    stayOnTop = Qt.WindowStaysOnTopHint if self.windowFlags() & Qt.WindowStaysOnTopHint else 0
    self.setWindowFlags(Qt.FramelessWindowHint | stayOnTop)

    self.windowEffect.enableBlurBehindWindow(self.winId())
    self.windowEffect.addWindowAnimation(self.winId())

    self.windowEffect.setAcrylicEffect(self.winId())
    if isGreaterEqualWin11():
        self.windowEffect.addShadowEffect(self.winId())

class CustomSplashScreen(SplashScreen):

    def finish(self):
        """ fade out splash screen """
        opacityEffect = QGraphicsOpacityEffect(self)
        opacityEffect.setOpacity(1)
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

        self.setMicaEffectEnabled(False)

        self.initWindow()

        # create sub interface
        self.taskInterface = TaskInterface(self)
        self.settingInterface = SettingInterface(self)
        # self.debugInterface = DebugInterface(self)

        # add items to navigation interface
        self.initNavigation()

        # 允许拖拽
        self.setAcceptDrops(True)

        # 自定义主题信号连接
        self.themeChangedListener = None
        self.__onCustomThemeModeChanged(cfg.customThemeMode.value)
        cfg.customThemeMode.valueChanged.connect(self.__onCustomThemeModeChanged)
        signalBus.appErrorSig.connect(self.onAppError)
        signalBus.showMainWindow.connect(lambda :bringWindowToTop(self))

        # 设置背景特效
        self.applyBackgroundEffectByCfg()

        # 创建未完成的任务
        historyFile = Path("{}/Ghost Downloader 记录文件".format(cfg.appPath))
        if historyFile.exists():
            f = open(historyFile, 'rb')
            try:
                while True:
                    taskRecord = pickle.load(f)
                    logger.debug(f"Unfinished Task is following: {taskRecord}")
                    addDownloadTask(taskRecord['url'], taskRecord['fileName'], taskRecord['filePath'], taskRecord['headers'], taskRecord['status'], taskRecord['blockNum'],  True, taskRecord['fileSize'])
            except EOFError:  # 读取完毕
                f.close()
            except Exception as e:
                logger.error(f"Failed to load unfinished task: {e}")
                f.close()
                historyFile.unlink()
                historyFile.touch()
        else:
            historyFile.touch()

        # 启动浏览器扩展服务器和剪切板监听器
        self.browserExtensionServer = None
        self.clipboard = None

        if cfg.enableBrowserExtension.value:
            self.runBrowserExtensionServer()

        if cfg.enableClipboardListener.value:
            self.runClipboardListener()

        # 创建托盘
        self.tray = CustomSystemTrayIcon(self)
        self.tray.show()

        # 检查更新
        if cfg.checkUpdateAtStartUp.value:
            checkUpdate(self)

        self.splashScreen.finish()

    def systemTitleBarRect(self, size: QSize) -> QRect:
        """重写 macOS 三大件到左上角"""
        return QRect(0, 0 if self.isFullScreen() else 9, 75, size.height())

    def __onCustomThemeModeChanged(self, value: str):
        if value == 'System':
            # 创建检测主题色更改线程
            self.themeChangedListener = ThemeChangedListener()
            self.themeChangedListener.themeChanged.connect(self.toggleTheme)
            self.themeChangedListener.start()
            setTheme(Theme.AUTO, save=False)
            self.applyBackgroundEffectByCfg()
        elif value == 'Dark':
            if self.themeChangedListener:
                self.themeChangedListener.terminate()
                self.themeChangedListener.deleteLater()
                self.themeChangedListener = None
            setTheme(Theme.DARK, save=False)
            self.applyBackgroundEffectByCfg()
        else:
            if self.themeChangedListener:
                self.themeChangedListener.terminate()
                self.themeChangedListener.deleteLater()
                self.themeChangedListener = None
            setTheme(Theme.LIGHT, save=False)
            self.applyBackgroundEffectByCfg()

    def runClipboardListener(self):
        if not self.clipboard:
            self.clipboard = QApplication.clipboard()
            self.clipboard.dataChanged.connect(self.__clipboardChanged)

    def stopClipboardListener(self):
            self.clipboard.dataChanged.disconnect(self.__clipboardChanged)
            self.clipboard.deleteLater()
            self.clipboard = None

    def runBrowserExtensionServer(self):
        if not self.browserExtensionServer:
            self.browserExtensionServer = GhostDownloaderSocketServer(self)

    def stopBrowserExtensionServer(self):
        self.browserExtensionServer.server.close()
        self.browserExtensionServer.server.deleteLater()
        self.browserExtensionServer.deleteLater()

        self.browserExtensionServer = None

    def toggleTheme(self, callback: str):
        if callback == 'Dark':  # MS 特性，需要重试
            setTheme(Theme.DARK, save=False, lazy=True)
            if cfg.backgroundEffect.value in ['Mica', 'MicaBlur', 'MicaAlt']:
                QTimer.singleShot(500, self.applyBackgroundEffectByCfg)

        elif callback == 'Light':
            setTheme(Theme.LIGHT, save=False, lazy=True)

        self.applyBackgroundEffectByCfg()

    def _normalBackgroundColor(self):
        if self.styleSheet() == "":
            return self._darkBackgroundColor if isDarkTheme() else self._lightBackgroundColor

        return QColor(0, 0, 0, 0)

    def applyBackgroundEffectByCfg(self):
        if sys.platform == 'win32':
            self.windowEffect.removeBackgroundEffect(self.winId())

            _ = cfg.customThemeMode.value

            if _ == 'System':
                _ = True if darkdetect.isDark() else False
            elif _ == 'Dark':
                _ = True
            elif _ == 'Light':
                _ = False

            if cfg.backgroundEffect.value == 'Acrylic':
                self.setStyleSheet("background-color: transparent")
                self.windowEffect.setAcrylicEffect(self.winId(), "00000030" if _ else "FFFFFF30")
            elif cfg.backgroundEffect.value == 'Mica':
                self.setStyleSheet("background-color: transparent")
                self.windowEffect.setMicaEffect(self.winId(), _)
            elif cfg.backgroundEffect.value == 'MicaBlur':
                self.windowEffect.setMicaEffect(self.winId(), _, isBlur=True)
                self.setStyleSheet("background-color: transparent")
            elif cfg.backgroundEffect.value == 'MicaAlt':
                self.windowEffect.setMicaEffect(self.winId(), _, isAlt=True)
                self.setStyleSheet("background-color: transparent")
            elif cfg.backgroundEffect.value == 'Aero':
                self.windowEffect.setAeroEffect(self.winId())
                self.setStyleSheet("background-color: transparent")
                if isLessThanWin10():
                    self.titleBar.closeBtn.hide()
                    self.titleBar.minBtn.hide()
                    self.titleBar.maxBtn.hide()
            elif cfg.backgroundEffect.value == 'None':
                self.setStyleSheet("")
                if isLessThanWin10():
                    self.titleBar.closeBtn.show()
                    self.titleBar.minBtn.show()
                    self.titleBar.maxBtn.show()

    def initNavigation(self):
        # add navigation items
        self.addSubInterface(self.taskInterface, FIF.DOWNLOAD, self.tr("任务列表"))
        self.navigationInterface.addItem(
            routeKey='addTaskButton',
            text=self.tr('新建任务'),
            selectable=False,
            icon=FIF.ADD,
            onClick=lambda:self.showAddTaskDialog(),  # 否则会传奇怪的参数
            position=NavigationItemPosition.TOP,
        )

        # self.addSubInterface(self.debugInterface, FIF.DEVELOPER_TOOLS, "调试信息")
        # add custom widget to bottom
        self.addSubInterface(self.settingInterface, FIF.SETTING, self.tr("设置"), position=NavigationItemPosition.BOTTOM)

    def initWindow(self):

        if cfg.geometry.value == "Default":
            self.resize(960, 780)
            desktop = QApplication.screens()[0].availableGeometry()
            w, h = desktop.width(), desktop.height()
            self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)
        else:
            try:
                self.setGeometry(cfg.get(cfg.geometry))
            except Exception as e:
                logger.error(f"Failed to restore geometry: {e}")
                cfg.set(cfg.geometry, "Default")

                self.resize(960, 780)
                desktop = QApplication.screens()[0].availableGeometry()
                w, h = desktop.width(), desktop.height()
                self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)

        self.setWindowIcon(QIcon(':/image/logo.png'))
        self.setWindowTitle('Ghost Downloader')

        if sys.platform == 'darwin':
            self.titleBar.hBoxLayout.insertSpacing(0, 58)

        if sys.platform == 'darwin':
            self.titleBar.maxBtn.hide()

        # create splash screen
        self.splashScreen = CustomSplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(QSize(106, 106))
        self.splashScreen.raise_()

        self.show()

        QApplication.processEvents()

    def onAppError(self, message: str):
        """ app error slot """
        QApplication.clipboard().setText(message)
        showMessageBox(
            self,
            self.tr("意料之外的错误!"),
            self.tr("错误消息已写入粘贴板和日志。是否报告?"),
            True,
            lambda: QDesktopServices.openUrl(QUrl(FEEDBACK_URL))
        )

    def showAddTaskDialog(self, text:str="", headers:dict=None):
        AddTaskOptionDialog.showAddTaskOptionDialog(text, self, headers)

    def closeEvent(self, event):
        # 拦截关闭事件，隐藏窗口而不是退出
        event.ignore()
        # 保存窗口位置，最大化时不保存
        if not self.isMaximized():
            cfg.set(cfg.geometry, self.geometry())

        self.hide()

    def nativeEvent(self, eventType, message):
        # 处理窗口重复打开事件
        if eventType == "windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(message.__int__())

            # WIN_USER = 1024
            if msg.message == 1024 + 1:
                bringWindowToTop(self)
                return True, 0

        return super().nativeEvent(eventType, message)

    def dragEnterEvent(self, event: QDragEnterEvent):
        logger.debug(f'Get event: {event}')
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def __setUrlsAndShowAddTaskMsg(self, text):
        QTimer.singleShot(10, lambda: self.showAddTaskDialog(text))

    def dropEvent(self, event: QDropEvent):
        mime = event.mimeData()
        if mime.hasUrls():
            urls = mime.urls()
            text = '\n'.join([url.toString() for url in urls if url.toString().startswith('http')])
        elif mime.hasText():
            text = mime.text()
        else:
            return

        if text:
            self.__setUrlsAndShowAddTaskMsg(text)

        event.accept()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Paste):
            text = self.clipboard.text()
            self.__setUrlsAndShowAddTaskMsg(text)
        else:
            super().keyPressEvent(event)

    def __checkUrl(self, url):
        try:
            _, fileName, __ = getLinkInfo(url, Headers)
            if fileName.lower().endswith(tuple(attachmentTypes.split())):
                return url
            return
        except ValueError:
            return False

    def __clipboardChanged(self):
        try:
            mime = self.clipboard.mimeData()
            if mime.data('application/x-gd3-copy') != b'':  # if not empty
                logger.debug("Clipboard changed from software itself")
                return  # 当剪贴板事件来源于软件本身时, 不执行后续代码
            if mime.hasText():
                urls = mime.text().lstrip().rstrip().split('\n')  # .strip()主要去两头的空格
            elif mime.hasUrls():
                urls = [url.toString() for url in mime.urls()]
            else:
                return

            results = []

            for url in urls:
                if self.__checkUrl(url):
                    results.append(url)
                else:
                    logger.debug(f"Invalid url: {url}")

            if not results:
                return

            results = '\n'.join(results)

            logger.debug(f"Clipboard changed: {results}")
            bringWindowToTop(self)
            self.__setUrlsAndShowAddTaskMsg(results)
        except Exception as e:
            logger.warning(f"Failed to check clipboard: {e}")

if isGreaterEqualWin10():   # 否则 Win 10 亚克力效果失效
    MainWindow.updateFrameless = updateFrameless
