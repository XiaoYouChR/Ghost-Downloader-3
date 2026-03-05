import niquests
from PySide6.QtCore import QRect, QPropertyAnimation, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QDialog
from loguru import logger
from qfluentwidgets import MSFluentWindow, SplashScreen, FluentIcon, NavigationItemPosition, InfoBar, InfoBarPosition, \
    PushButton, PrimaryPushButton

from app.services.feature_service import featureService
from app.supports.config import cfg
from app.supports.recorder import taskRecorder
from app.supports.utils import getProxies
from app.view.components.add_task_dialog import AddTaskDialog
from app.view.components.dialogs import ReleaseInfoDialog
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
        self.initPagesAndNavigation()

        QApplication.processEvents()

        # TODO show update tooltip for Test
        self.showUpdateToolTip({"version": "0.0.1", "content": "This is a test tooltip."})

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
                logger.error(f"Failed to restore geometry: {e}")
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

    def showAddTaskDialog(self, triggeredByUser: bool = False):
        if AddTaskDialog.display(parent=self) == QDialog.DialogCode.Accepted:
            for task in AddTaskDialog.instance.parseResultGroup.getAllTasks():
                try:
                    card = featureService.createTaskCard(task, self)
                    taskRecorder.add(task, False)
                    self.taskPage.addCard(card)
                    card.resumeTask()
                except Exception as e:
                    logger.error(f"无法创建任务卡片: {repr(e)}")

            taskRecorder.flush()

            AddTaskDialog.instance.urlEdit.clear()
            AddTaskDialog.instance.parseResultGroup.clearResults()

    def showUpdateToolTip(self, payload: dict):
        infoBar = InfoBar(
            icon=FluentIcon.CLOUD,
            title=self.tr('检测到新版本'),
            content=payload["version"],
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            duration=-1,
            position=InfoBarPosition.BOTTOM_RIGHT,
            parent=self
        )
        infoBar.widgetLayout.addSpacing(10)
        infoBar.addWidget(PrimaryPushButton(FluentIcon.DOWNLOAD, self.tr('立即下载')))
        detailButton = PushButton(FluentIcon.CHAT, self.tr('查看版本详细'))
        detailButton.clicked.connect(lambda: self._showReleaseDialog(payload))
        infoBar.addWidget(detailButton)

        infoBar.addWidget(PushButton(FluentIcon.HEART, self.tr('请作者喝咖啡')))
        # infoBar.setCustomBackgroundColor("white", "#2a2a2a")
        infoBar.show()

    def _showReleaseDialog(self, releaseData: dict):
        """显示 Release 详情对话框"""
        releaseData = niquests.get(url="https://api.github.com/repos/XiaoYouChR/Ghost-Downloader-3/releases/latest", headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.64"},
                                allow_redirects=True, proxies=getProxies()).json()
        dialog = ReleaseInfoDialog(releaseData, parent=self)
        dialog.exec()
