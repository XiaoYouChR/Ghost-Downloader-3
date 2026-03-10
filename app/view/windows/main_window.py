from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QRect, QPropertyAnimation, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QDialog
from loguru import logger
from qfluentwidgets import MSFluentWindow, SplashScreen, FluentIcon, NavigationItemPosition, InfoBar, InfoBarPosition, \
    PushButton, PrimaryPushButton

from app.services.browser_service import BrowserService
from app.services.core_service import coreService
from app.services.feature_service import featureService
from app.supports.config import cfg, DEFAULT_HEADERS, AUTHOR_URL, VERSION, FEEDBACK_URL
from app.supports.recorder import taskRecorder
from app.supports.signal_bus import signalBus
from app.supports.update import fetchLatestRelease, hasNewerRelease, releaseVersion, selectCurrentPlatformAsset
from app.supports.utils import getProxies, bringWindowToTop, showMessageBox
from app.view.components.add_task_dialog import AddTaskDialog
from app.view.components.release_info_dialog import ReleaseInfoDialog
from app.view.components.tray import SystemTrayIcon
from app.view.pages.setting_page import SettingPage
from app.view.pages.task_page import TaskPage


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


class MainWindow(MSFluentWindow):
    def __init__(self, isSilently = False):
        super().__init__(parent = None)

        self.initWindow()
        if not isSilently:
            self.initSplashScreen()

        QApplication.processEvents()

        self.initPagesAndNavigation()

        self.clipboard: "QClipboard" = None
        self.tray = SystemTrayIcon(self)
        self.tray.show()
        self.browserService = BrowserService(self)

        self.connectSignalToSlot()
        self._syncClipboardListener()
        if cfg.checkUpdateAtStartUp.value:
            self.checkForUpdates()

    def connectSignalToSlot(self):
        signalBus.showMainWindow.connect(lambda: bringWindowToTop(self))
        signalBus.catchException.connect(self._onExceptionCaught)
        cfg.enableClipboardListener.valueChanged.connect(self._syncClipboardListener)

    def _syncClipboardListener(self):
        if self.clipboard is None:
            self.clipboard = QApplication.clipboard()
            if not cfg.enableClipboardListener.value:
                return

        if cfg.enableClipboardListener.value:
            self.clipboard.dataChanged.connect(self._onClipboardDataChanged)
        else:
            self.clipboard.dataChanged.disconnect(self._onClipboardDataChanged)


    def _extractClipboardUrls(self, text: str) -> list[str]:
        urls = []
        for rawLine in text.splitlines():
            url = rawLine.strip()
            if not url:
                continue

            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc or parsed.geturl() != url:
                continue

            if featureService.canHandle(url):
                urls.append(url)

        return urls

    def _onClipboardDataChanged(self):
        urls = self._extractClipboardUrls(QApplication.clipboard().text())
        if not urls:
            return

        bringWindowToTop(self)
        self.showAddTaskDialog(urls=urls)

    def _onExceptionCaught(self, message: str):
        bringWindowToTop(self)
        showMessageBox(
            self,
            self.tr("程序发生异常"),
            self.tr("点击“确定”后将复制错误信息并打开反馈页面。\n{0}").format(message),
            showYesButton=True,
            yesSlot=lambda: self._copyExceptionAndOpenFeedback(message),
        )

    def _copyExceptionAndOpenFeedback(self, message: str):
        QApplication.clipboard().setText(message)
        QDesktopServices.openUrl(QUrl(FEEDBACK_URL))

    def getAddTaskDialog(self) -> AddTaskDialog:
        if AddTaskDialog.instance is None:
            instance = AddTaskDialog.initialize(self)
            instance.taskConfirmed.connect(self.addTask)

        return AddTaskDialog.instance

    def _restoreGeometry(self):
        self.resize(960, 540)
        desktop = QApplication.primaryScreen().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)

    def initWindow(self):
        # Center the window
        cfgGeometry: QRect = cfg.geometry.value
        x, y, w, h = cfgGeometry.x(), cfgGeometry.y(), cfgGeometry.width(), cfgGeometry.height()
        if x == 0 and y == 0 and w == 0 and h == 0:
            self._restoreGeometry()
        else:
            try:
                self.setGeometry(cfg.get(cfg.geometry))
            except Exception as e:
                logger.opt(exception=e).error("Failed to restore geometry")
                cfg.set(cfg.geometry, QRect(0, 0, 0, 0))
                self._restoreGeometry()
        # Init Window
        self.setWindowIcon(QIcon(':/image/logo.png'))
        self.setWindowTitle('Ghost Downloader')

    def initSplashScreen(self):
        self.splashScreen = CustomSplashScreen(self.windowIcon(), self, enableShadow=False)
        self.splashScreen.raise_()
        self.show()

    def initPagesAndNavigation(self):
        self.taskPage = TaskPage(self)
        self.settingPage = SettingPage(self)
        self.addSubInterface(self.taskPage, FluentIcon.DOWNLOAD, self.tr("下载任务"), position=NavigationItemPosition.TOP)
        self.navigationInterface.addItem(
            routeKey='addTaskButton',
            text=self.tr('新建任务'),
            selectable=False,
            icon=FluentIcon.ADD,
            onClick=self.showAddTaskDialog,
            position=NavigationItemPosition.TOP,
        )
        self.addSubInterface(self.settingPage, FluentIcon.SETTING, self.tr("设置"), position=NavigationItemPosition.BOTTOM)

    def showAddTaskDialog(self, triggeredByUser: bool = False, urls: list[str] | None = None):
        dialog = self.getAddTaskDialog()

        if urls:
            dialog.appendUrls(urls)

        if dialog.isVisible():
            dialog.raise_()
            dialog.activateWindow()
            return

        if dialog.exec() == QDialog.DialogCode.Accepted:
            for task in dialog.takeConfirmedTasks():
                self.addTask(task)

    def addTask(self, task) -> bool:
        try:
            card = featureService.createTaskCard(task, self)
            taskRecorder.add(task, False)
            self.taskPage.addCard(card)
            card.resumeTask()
            taskRecorder.flush()
            return True
        except Exception as e:
            logger.opt(exception=e).error("无法创建任务卡片 {}", getattr(task, "title", "Unknown"))
            return False

    def closeEvent(self, event, /):
        event.ignore()
        if not self.isMaximized():
            cfg.set(cfg.geometry, self.geometry())

        self.hide()

    # 检查更新
    def checkForUpdates(self, manual: bool = False):
        if manual:
            InfoBar.info(
                self.tr("检查更新"),
                self.tr("正在检查更新..."),
                duration=1500,
                position=InfoBarPosition.BOTTOM_RIGHT,
                parent=self,
            )

        coreService.runCoroutine(
            fetchLatestRelease(),
            lambda releaseData, error, manual=manual: self._onLatestReleaseLoaded(releaseData, error, manual),
        )

    def _onLatestReleaseLoaded(self, releaseData: dict, error: str | None, manual: bool):
        if error:
            logger.warning("检查更新失败: {}", error)
            if manual:
                InfoBar.error(
                    self.tr("检查更新失败"),
                    self.tr("无法获取最新版本信息"),
                    duration=3000,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    parent=self,
                )
            return

        latestVersion = releaseVersion(releaseData)
        if not hasNewerRelease(releaseData):
            if manual:
                InfoBar.success(
                    self.tr("当前已是最新版本"),
                    self.tr("当前版本 {0}，最新 Release {1}").format(VERSION, latestVersion),
                    duration=3000,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    parent=self,
                )
            return

        if manual:
            self._showReleaseDialog(releaseData)
            return

        version = releaseVersion(releaseData)
        infoBar = InfoBar(
            icon=FluentIcon.CLOUD,
            title=self.tr('检测到新版本'),
            content=self.tr("最新版本: {0}").format(version),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            duration=-1,
            position=InfoBarPosition.BOTTOM_RIGHT,
            parent=self
        )
        infoBar.widgetLayout.addSpacing(10)
        downloadButton = PrimaryPushButton(FluentIcon.DOWNLOAD, self.tr('立即下载'))
        downloadButton.clicked.connect(lambda: self._downloadMatchedReleaseAsset(releaseData))
        infoBar.addWidget(downloadButton)
        detailButton = PushButton(FluentIcon.CHAT, self.tr('查看版本详细'))
        detailButton.clicked.connect(lambda: self._showReleaseDialog(releaseData))
        infoBar.addWidget(detailButton)

        sponsorButton = PushButton(FluentIcon.HEART, self.tr('请作者喝咖啡'))
        sponsorButton.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(AUTHOR_URL)))
        infoBar.addWidget(sponsorButton)
        infoBar.show()

    def _downloadMatchedReleaseAsset(self, releaseData: dict):
        asset = selectCurrentPlatformAsset(releaseData)
        if asset is None:
            InfoBar.warning(
                self.tr("未找到适配的安装包"),
                self.tr("已打开版本详情，请手动选择要下载的文件"),
                duration=3000,
                position=InfoBarPosition.BOTTOM_RIGHT,
                parent=self,
            )
            self._showReleaseDialog(releaseData)
            return

        self._downloadReleaseAsset(asset)

    def _downloadReleaseAsset(self, asset: dict):
        assetName = asset["name"]
        payload = {
            "url": asset["browser_download_url"],
            "headers": DEFAULT_HEADERS,
            "proxies": getProxies(),
            "path": Path(cfg.downloadFolder.value),
            "preBlockNum": cfg.preBlockNum.value,
        }
        coreService.parseUrl(
            payload,
            lambda task, error, assetName=assetName: self._onReleaseAssetParsed(assetName, task, error),
        )

    def _onReleaseAssetParsed(self, assetName: str, task, error: str | None):
        if error:
            logger.warning("创建更新下载任务失败 {}: {}", assetName, error)
            InfoBar.error(
                self.tr("创建下载任务失败"),
                assetName,
                duration=3000,
                position=InfoBarPosition.BOTTOM_RIGHT,
                parent=self,
            )
            return

        if self.addTask(task):
            InfoBar.success(
                self.tr("已添加下载任务"),
                assetName,
                duration=2000,
                position=InfoBarPosition.BOTTOM_RIGHT,
                parent=self,
            )

    def _showReleaseDialog(self, releaseData: dict):
        dialog = ReleaseInfoDialog(releaseData, self, False)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._downloadReleaseAsset(dialog.selectedAsset())
        dialog.deleteLater()
