from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from qfluentwidgets import CardWidget, RoundMenu, Action
from qfluentwidgets import FluentIcon as FIF

from .Ui_SystemInfoCard import Ui_SystemInfoCard
from ..components.download_option_dialog import DownloadOptionDialog


class SystemInfoCard(CardWidget, Ui_SystemInfoCard):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setupUi(self)

        self.List = []
        self.Video = ""
        self.pixmap: QPixmap

        self.PrimarySplitPushButton.setText("      下载      ")
        self.Menu = RoundMenu(parent=self)
        self.VideoAction = Action(FIF.VIDEO, "视频")
        self.Menu.addAction(self.VideoAction)
        self.PrimarySplitPushButton.setFlyout(self.Menu)

    def connect_signal_to_slot(self):
        self.VideoAction.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(self.Video)))
        self.PrimarySplitPushButton.clicked.connect(self.open_download_messagebox)

    def open_download_messagebox(self):
        w = DownloadOptionDialog(self.parent().parent().parent().parent().parent().parent(), self.List,
                                 {"Pixmap": self.pixmap, "Name": self.TitleLabel.text()})
        w.exec()
