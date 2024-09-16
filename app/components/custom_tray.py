from PySide6.QtCore import QRect
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QSystemTrayIcon, QApplication
from qfluentwidgets import Action
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets.components.material import AcrylicMenu
from shiboken6.Shiboken import delete


class FixedAcrylicSystemTrayMenu(AcrylicMenu):
    """ 修复背景获取偏移的问题 """

    def showEvent(self, e):
        super().showEvent(e)
        self.adjustPosition()
        self.view.acrylicBrush.grabImage(QRect(self.pos() + self.view.pos(), self.view.size()))

class CustomSystemTrayIcon(QSystemTrayIcon):

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setIcon(parent.windowIcon())
        self.setToolTip('Ghost Downloader 🥰')

        self.menu = FixedAcrylicSystemTrayMenu(parent=parent)

        self.showAction = Action(QIcon(":/image/logo.png") ,'仪表盘', self.menu)
        self.showAction.triggered.connect(self.__onShowActionTriggered)
        self.menu.addAction(self.showAction)

        self.allPauseAction = Action(FIF.PLAY, '全部开始', self.menu)
        self.allPauseAction.triggered.connect(self.__onAllStartActionTriggered)
        self.menu.addAction(self.allPauseAction)

        self.allPauseAction = Action(FIF.PAUSE, '全部暂停', self.menu)
        self.allPauseAction.triggered.connect(self.__onAllPauseActionTriggered)
        self.menu.addAction(self.allPauseAction)

        self.quitAction = Action(FIF.CLOSE, '退出程序', self.menu)
        self.quitAction.triggered.connect(self.__onQuitActionTriggered)
        self.menu.addAction(self.quitAction)

        self.setContextMenu(self.menu)

        self.activated.connect(self.onTrayIconClick)
        self.messageClicked.connect(self.__onShowActionTriggered)

    def __onShowActionTriggered(self):
        self.parent().show()
        if self.parent().isMinimized():
            self.parent().showNormal()
        # 激活窗口，使其显示在最前面
        self.parent().activateWindow()

    def __onAllStartActionTriggered(self):
        self.parent().taskInterface.allStartTasks()

    def __onAllPauseActionTriggered(self):
        self.parent().taskInterface.allPauseTasks()
    
    def __onQuitActionTriggered(self):
        self.parent().themeChangedListener.terminate()

        for i in self.parent().taskInterface.cards:  # 是为了不写入历史记录安全的退出
            if i.status == 'working':
                for j in i.task.tasks:
                    j.cancel()

                i.task.file.close()
                i.task.ghdFile.close()
                i.task.terminate()
                i.task.deleteLater()

                delete(i.task)

        QApplication.quit()

    def onTrayIconClick(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.__onShowActionTriggered()