from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QSystemTrayIcon, QApplication
from qfluentwidgets import Action
from qfluentwidgets import FluentIcon as FIF

from app.common.methods import bringWindowToTop
from app.components.custom_components import FixedAcrylicMenu


class CustomSystemTrayIcon(QSystemTrayIcon):

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setIcon(parent.windowIcon())
        self.setToolTip('Ghost Downloader 🥰')

        self.menu = FixedAcrylicMenu(parent=parent)

        self.showAction = Action(QIcon(":/image/logo_withoutBackground.png"), self.tr('仪表盘'), self.menu)
        self.showAction.triggered.connect(self.__onShowActionTriggered)
        self.menu.addAction(self.showAction)

        self.allPauseAction = Action(FIF.PLAY, self.tr('全部开始'), self.menu)
        self.allPauseAction.triggered.connect(self.__onAllStartActionTriggered)
        self.menu.addAction(self.allPauseAction)

        self.allPauseAction = Action(FIF.PAUSE, self.tr('全部暂停'), self.menu)
        self.allPauseAction.triggered.connect(self.__onAllPauseActionTriggered)
        self.menu.addAction(self.allPauseAction)

        self.quitAction = Action(FIF.CLOSE, self.tr('退出程序'), self.menu)
        self.quitAction.triggered.connect(self.__onQuitActionTriggered)
        self.menu.addAction(self.quitAction)

        self.setContextMenu(self.menu)

        self.activated.connect(self.onTrayIconClick)
        self.messageClicked.connect(self.__onShowActionTriggered)

    def __onShowActionTriggered(self):
        bringWindowToTop(self.parent())

    def __onAllStartActionTriggered(self):
        self.parent().taskInterface.allStartTasks()

    def __onAllPauseActionTriggered(self):
        self.parent().taskInterface.allPauseTasks()

    def __onQuitActionTriggered(self):
        if self.parent().themeChangedListener:
            self.parent().themeChangedListener.terminate()

        for i in self.parent().taskInterface.cards:  # 是为了不写入历史记录安全的退出
            if i.status == 'working':
                i.task.stop()

                # self.task.terminate()
                i.task.wait()
                i.task.deleteLater()

        QApplication.quit()

    def onTrayIconClick(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.__onShowActionTriggered()
