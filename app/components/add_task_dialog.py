import os
import re
from pathlib import Path
from threading import Thread

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
    __addTableRowSignal = Signal(str, str, str)  # fileName, fileSize, Url, 同理因为int最大值仅支持到2^31 PyQt无法定义int64 故只能使用str代替
    __gotWrong = Signal(str, int) # error, index

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
        self.laterAction.triggered.connect(self.__onLaterActionTriggered)
        self.taskTableWidget.itemChanged.connect(self.__onTaskTableWidgetItemChanged)
        self.linkTextEdit.textChanged.connect(self.__onLinkTextChanged)
        self.__addTableRowSignal.connect(self.__addTableRow)
        self.__gotWrong.connect(self.__handleWrong)

    def __handleWrong(self, error: str, index: int):
        InfoBar.error(
            title='错误',
            content=f"解析第 {index} 个链接时遇到错误: {error}",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            # position='Custom',   # NOTE: use custom info bar manager
            duration=10000,
            parent=self.parent()
        )

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

        for i in range(self.taskTableWidget.rowCount()):
            item = self.taskTableWidget.item(i, 0)

            signalBus.addTaskSignal.emit(item.data(1),
                                         str(path), self.blockNumCard.configItem.value,
                                         item.text(), "working", False)

        self.close()

    def __onLaterActionTriggered(self):
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

        for i in range(self.taskTableWidget.rowCount()):
            item = self.taskTableWidget.item(i, 0)

            signalBus.addTaskSignal.emit(item.data(1),
                                         str(path), self.blockNumCard.configItem.value,
                                         item.text(), "paused", False)

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

    def __handleUrl(self, url: str, index: int):
        try:
            _url, fileName, fileSize = getLinkInfo(url, Headers)
            self.__addTableRowSignal.emit(fileName, str(fileSize), url)  # 不希望使用重定向后的url，故使用原始url
            
        except Exception as e:
            self.__gotWrong.emit(repr(e), index)


    def __addTableRow(self, fileName: str, fileSize: str, url: str):
        """ add table row slot """
        self.taskTableWidget.insertRow(self.taskTableWidget.rowCount())
        _ = QTableWidgetItem(fileName)
        _.setData(1, url) # 记录 Url
        _.setData(2, fileName) # 设置默认值, 当用户修改后的内容为空是，使用默认值替换
        self.taskTableWidget.setItem(self.taskTableWidget.rowCount() - 1, 0, _)
        _ = QTableWidgetItem(getReadableSize(int(fileSize)))
        _.setFlags(Qt.ItemIsEnabled)  # 禁止编辑
        self.taskTableWidget.setItem(self.taskTableWidget.rowCount() - 1, 1, _)

        # self.taskTableWidget.resizeColumnsToContents()

    def __onTaskTableWidgetItemChanged(self, item: QTableWidgetItem):
        """ task table widget item changed slot """
        if item.text() == '':
            item.setText(item.data(2))

    def __processTextChange(self):
        """ link text changed slot """
        # 清除所有行
        self.taskTableWidget.setRowCount(0)
        self.threads = []
        
        self.yesButton.setEnabled(False)

        text: list = self.linkTextEdit.toPlainText().split("\n")

        for index, url in enumerate(text, start=1):

            _ = urlRe.search(url)

            if _:
                self.threads.append(Thread(target=self.__handleUrl, args=(url, index), daemon=True))

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

        if self.threads:
            for thread in self.threads:
                thread.start()

            Thread(target=self.__waitForThreads, daemon=True).start()
            
    def __waitForThreads(self):
        for thread in self.threads:
            thread.join()

        if self.taskTableWidget.rowCount() >= 0:
            self.yesButton.setEnabled(True)