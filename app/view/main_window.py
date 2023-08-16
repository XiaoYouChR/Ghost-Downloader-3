# coding: utf-8
from typing import List
from PySide6.QtCore import Qt, Signal, QEasingCurve, QUrl, QSize
from PySide6.QtGui import QIcon, QDesktopServices
from PySide6.QtWidgets import QApplication, QHBoxLayout, QFrame, QWidget

from qfluentwidgets import NavigationAvatarWidget, NavigationItemPosition, MessageBox, FluentWindow, SplashScreen
from qfluentwidgets import FluentIcon as FIF

from .home_interface import HomeInterface
from .task_interface import TaskInterface


class MainWindow(FluentWindow):

    def __init__(self):
        super().__init__()
        self.initWindow()

        # create sub interface
        self.homeInterface = HomeInterface(self)
        self.taskInterface = TaskInterface(self)

        # add items to navigation interface
        self.initNavigation()
        self.splashScreen.finish()

    def initNavigation(self):
        # add navigation items
        self.addSubInterface(self.homeInterface, FIF.HOME, "主页")
        self.addSubInterface(self.taskInterface, FIF.DOWNLOAD, "任务列表")
        self.addSubInterface(self.taskInterface, FIF.DOWNLOAD, "任务列表")
        # add custom widget to bottom
        self.navigationInterface.addItem(
            routeKey='avatar',
            text='关于',
            icon=FIF.INFO,
            onClick=self.showInfoMessageBox,
            position=NavigationItemPosition.BOTTOM,
        )

    def initWindow(self):
        self.resize(960, 780)
        self.setWindowIcon(QIcon(':/icon/logo.png'))
        self.setWindowTitle('Ghost-Downloader-3')

        # create splash screen
        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(QSize(106, 106))
        self.splashScreen.raise_()

        desktop = QApplication.screens()[0].availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w//2 - self.width()//2, h//2 - self.height()//2)
        self.show()
        QApplication.processEvents()

    def showInfoMessageBox(self):
        w = MessageBox(
            '关于 Ghost-Downloader-3',
            '当前版本 2.9.9-alpha\n屎山作者 晓游ChR\n版本亮点 下载功能前所未有的稳定（估计）\n目前存在的问题 界面细节&进度在任务restart后显示不准确',
            self
        )
        w.yesButton.setText('了解作者')
        w.cancelButton.setText('关闭窗口')

        if w.exec():
            QDesktopServices.openUrl(QUrl("https://space.bilibili.com/437313511"))