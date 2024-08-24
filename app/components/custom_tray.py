from PySide6.QtCore import QRect
from PySide6.QtWidgets import QSystemTrayIcon, QApplication
from loguru import logger
from qfluentwidgets import Action, MessageBox
from qfluentwidgets.components.material import AcrylicMenu


class FixedAcrylicSystemTrayMenu(AcrylicMenu):
    """ 修复背景获取便宜的问题 """

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

        # self.view.acrylicBrush.grabImage(QRect(self.pos() + self.view.pos(), self.view.size()))


        self.showAction = Action('🎤 显示主窗口', self.menu)
        self.showAction.triggered.connect(self.showMainWindow)
        self.menu.addAction(self.showAction)

        self.ikunAction = Action('🏀 唱跳RAP', self.menu)
        self.ikunAction.triggered.connect(self.ikun)
        self.menu.addAction(self.ikunAction)

        self.quitAction = Action('🕺 退出程序', self.menu)
        self.quitAction.triggered.connect(self.quitApplication)
        self.menu.addAction(self.quitAction)

        self.setContextMenu(self.menu)

        self.activated.connect(self.onTrayIconClick)
        self.messageClicked.connect(self.showMainWindow)

    def showMainWindow(self):
        self.parent().show()
        if self.parent().isMinimized():
            self.parent().showNormal()
        # 激活窗口，使其显示在最前面
        self.parent().activateWindow()

    def ikun(self):
        self.parent().show()
        content = """巅峰产生虚伪的拥护，黄昏见证真正的使徒 🏀

                         ⠀⠰⢷⢿⠄
                   ⠀⠀⠀⠀⠀⣼⣷⣄
                   ⠀⠀⣤⣿⣇⣿⣿⣧⣿⡄
                   ⢴⠾⠋⠀⠀⠻⣿⣷⣿⣿⡀
                   ⠀⢀⣿⣿⡿⢿⠈⣿
                   ⠀⠀⠀⢠⣿⡿⠁⠀⡊⠀⠙
                   ⠀⠀⠀⢿⣿⠀⠀⠹⣿
                   ⠀⠀⠀⠀⠹⣷⡀⠀⣿⡄
                   ⠀⠀⠀⠀⣀⣼⣿⠀⢈⣧
        """
        w = MessageBox(
            title='坤家军！集合！',
            content=content,
            parent=self.parent()
        )
        w.yesButton.setText('献出心脏')
        w.cancelButton.setText('你干嘛~')
        w.exec()
    
    def quitApplication(self):
        self.parent().themeChangedListener.terminate()

        for i in self.parent().taskInterface.cards:
            if i.status == 'working':
                for j in i.task.workers:
                    try:
                        j.file.close()
                    except AttributeError as e:
                        logger.info(f"Task:{i.task.fileName}, users operate too quickly!, thread {i} error: {e}")
                    except Exception as e:
                        logger.warning(
                            f"Task:{i.task.fileName}, it seems that cannot cancel thread {i} occupancy of the file, error: {e}")
                    j.terminate()
                i.task.terminate()

        QApplication.quit()

    def onTrayIconClick(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.showMainWindow()