import os
import re
import threading
from pathlib import Path

from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFileDialog, QTableWidgetItem
from qfluentwidgets import PushSettingCard, RangeSettingCard, MessageBox, InfoBar, InfoBarPosition, FluentStyleSheet
from qfluentwidgets.common.icon import FluentIcon as FIF
from qfluentwidgets.components.dialog_box.mask_dialog_base import MaskDialogBase

from .Ui_AddTaskOptionDialog import Ui_AddTaskOptionDialog
from ..common.config import cfg
from ..common.download_task import Headers
from ..common.methods import getReadableSize, getLinkInfo
from ..common.signal_bus import signalBus

urlRe = re.compile(r"^" +
                   "(https?://)" +
                   "(?:\\S+(?::\\S*)?@)?" +
                   "(?:" +
                   "(?:[1-9]\\d?|1\\d\\d|2[01]\\d|22[0-3])" +
                   "(?:\\.(?:1?\\d{1,2}|2[0-4]\\d|25[0-5])){2}" +
                   "(\\.(?:[1-9]\\d?|1\\d\\d|2[0-4]\\d|25[0-4]))" +
                   "|" +
                   "((?:[a-z\\u00a1-\\uffff0-9]-*)*[a-z\\u00a1-\\uffff0-9]+)" +
                   '(?:\\.(?:[a-z\\u00a1-\\uffff0-9]-*)*[a-z\\u00a1-\\uffff0-9]+)*' +
                   "(\\.([a-z\\u00a1-\\uffff]{2,}))" +
                   ")" +
                   "(?::\\d{2,5})?" +
                   "(?:/\\S*)?" +
                   "$", re.IGNORECASE)


class AddTaskOptionDialog(MaskDialogBase, Ui_AddTaskOptionDialog):

    startSignal = Signal()
    __addTableRowSignal = Signal(str, str)  # fileName, fileSize, 同理因为int最大值仅支持到2^31 PyQt无法定义int64 故只能使用str代替

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        FluentStyleSheet.DIALOG.apply(self.widget)
        self.widget.setContentsMargins(11, 11, 11, 11)

        self.setShadowEffect(60, (0, 10), QColor(0, 0, 0, 50))
        self.setMaskColor(QColor(0, 0, 0, 76))
        self.setClosableOnMaskClicked(True)

        self.setupUi(self.widget)

        self.verticalLayout.setSpacing(8)
        self.widget.setLayout(self.verticalLayout)

        # Choose Folder Card
        self.downloadFolderCard = PushSettingCard(
            "选择下载目录",
            FIF.DOWNLOAD,
            "下载目录",
            cfg.downloadFolder.value,
            self.widget
        )

        # Choose Threading Card
        self.blockNumCard = RangeSettingCard(
            cfg.maxBlockNum,
            FIF.CLOUD,
            "下载线程数",
            '下载线程越多，下载越快，同时也越吃性能',
            self.widget
        )

        self.verticalLayout.insertWidget(4, self.downloadFolderCard)
        self.verticalLayout.insertWidget(5, self.blockNumCard)

        self.__connectSignalToSlot()

    def __connectSignalToSlot(self):
        self.downloadFolderCard.clicked.connect(
            self.__onDownloadFolderCardClicked)

        self.noButton.clicked.connect(self.close)
        self.yesButton.clicked.connect(self.__onYesButtonClicked)
        self.taskTableWidget.itemChanged.connect(self.__onTaskTableWidgetItemChanged)
        self.linkTextEdit.textChanged.connect(self.__onLinkTextChanged)
        self.__addTableRowSignal.connect(self.__addTableRow)

    def __onYesButtonClicked(self):
        path = Path(self.downloadFolderCard.contentLabel.text())

        # 检测路径是否有权限写入
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                MessageBox("错误", str(e), self)
        else:
            if not os.access(path, os.W_OK):
                MessageBox("错误", "似乎是没有权限向此目录写入文件", self)

        text = self.linkTextEdit.toPlainText().split("\n")

        for i, url in enumerate(text):  # 不希望在记录文件里写入重定向之后的Url，故使用用户输入的Url
            _ = urlRe.search(url)

            # fileName = self.taskTableWidget.item(i + 1, 0).text()

            if _:
                signalBus.addTaskSignal.emit(url,
                                             str(path), self.blockNumCard.configItem.value,
                                             self.taskTableWidget.item(i, 0).text(), "working", False)

        self.close()

    def __onDownloadFolderCardClicked(self):
        """ download folder card clicked slot """
        folder = QFileDialog.getExistingDirectory(
            self, "选择文件夹", "./")
        if not folder or self.downloadFolderCard.contentLabel.text() == folder:
            return

        self.downloadFolderCard.setContent(folder)


    def __onLinkTextChanged(self):
        if hasattr(self, '_timer'):
            self._timer.stop()

        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.__processTextChange)
        self._timer.start(1000)  # 1秒后处理

    def __handleUrl(self, url: str):
        url, fileName, fileSize = getLinkInfo(url, Headers)

        self.__addTableRowSignal.emit(fileName, str(fileSize))

    def __addTableRow(self, fileName: str, fileSize: str):
        """ add table row slot """
        self.taskTableWidget.insertRow(self.taskTableWidget.rowCount())
        _ = QTableWidgetItem(fileName)
        _.setData(1, fileName) # 设置默认值, 当用户修改后的内容为空是，使用默认值替换
        self.taskTableWidget.setItem(self.taskTableWidget.rowCount() - 1, 0, _)
        _ = QTableWidgetItem(getReadableSize(int(fileSize)))
        # _.setData(1, fileSize)
        _.setFlags(Qt.ItemIsEnabled)  # 禁止编辑
        self.taskTableWidget.setItem(self.taskTableWidget.rowCount() - 1, 1, _)

        self.taskTableWidget.resizeColumnsToContents()

    def __onTaskTableWidgetItemChanged(self, item: QTableWidgetItem):
        """ task table widget item changed slot """
        if item.text() == '':
            item.setText(item.data(1))

    def __processTextChange(self):
        """ link text changed slot """
        # 清除所有行
        self.taskTableWidget.setRowCount(0)

        text: list = self.linkTextEdit.toPlainText().split("\n")

        for index, url in enumerate(text, start=1):

            _ = urlRe.search(url)

            if _:
                self.yesButton.setEnabled(True)
                threading.Thread(target=self.__handleUrl, args=(url,), daemon=True).start()

            else:
                InfoBar.warning(
                    title='警告',
                    content=f"第{index}个链接无效!",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    # position='Custom',   # NOTE: use custom info bar manager
                    duration=1000,
                    parent=self.parent()
                )
