import os
import re
from pathlib import Path
from threading import Thread

from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFileDialog, QTableWidgetItem
from qfluentwidgets import PushSettingCard, RangeSettingCard, MessageBox, InfoBar, InfoBarPosition, FluentStyleSheet
from qfluentwidgets.common.icon import FluentIcon as FIF

from app.components.custom_mask_dialog_base import MaskDialogBase
from .Ui_AddTaskOptionDialog import Ui_AddTaskOptionDialog
from .custom_dialogs import EditHeadersDialog
from ..common.config import cfg, Headers
from ..common.methods import getReadableSize, getLinkInfo, addDownloadTask

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

        self.customHeaders = Headers.copy()

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

        self.blockNumCard = RangeSettingCard(
            cfg.preBlockNum,
            FIF.CLOUD,
            "下载线程数",
            '',
            self.widget
        )

        # Edit customHeaders Card
        self.editHeadersCard = PushSettingCard(
            "编辑请求标头",
            FIF.EDIT,
            "自定义请求标头",
            "",
            self.widget
        )

        self.verticalLayout.insertWidget(4, self.downloadFolderCard)
        self.verticalLayout.insertWidget(5, self.blockNumCard)
        self.verticalLayout.insertWidget(6, self.editHeadersCard)

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
        self.editHeadersCard.clicked.connect(self.__onEditHeadersCardClicked)

    def __handleWrong(self, error: str, index: int):
        InfoBar.error(
            title='错误',
            content=f"解析第 {index} 个链接时遇到错误: {error}",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=10000,
            parent=self.parent()
        )

    def __onEditHeadersCardClicked(self):
        newHeaders, ok = EditHeadersDialog(self, initialHeaders=self.customHeaders).getHeaders()
        if newHeaders and ok:
            self.customHeaders = newHeaders

    def __onYesButtonClicked(self):
        path = Path(self.downloadFolderCard.contentLabel.text())

        # 检测路径是否有权限写入
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                MessageBox("错误", repr(e), self)
        else:
            if not os.access(path, os.W_OK):
                MessageBox("错误", "似乎是没有权限向此目录写入文件", self)

        for i in range(self.taskTableWidget.rowCount()):
            item = self.taskTableWidget.item(i, 0)

            addDownloadTask(item.data(1), item.text(),  str(path), self.customHeaders, preBlockNum=self.blockNumCard.configItem.value)

        self.close()

    def __onLaterActionTriggered(self):
        path = Path(self.downloadFolderCard.contentLabel.text())

        # 检测路径是否有权限写入
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                MessageBox("错误", repr(e), self)
        else:
            if not os.access(path, os.W_OK):
                MessageBox("错误", "似乎是没有权限向此目录写入文件", self)

        for i in range(self.taskTableWidget.rowCount()):
            item = self.taskTableWidget.item(i, 0)

            addDownloadTask(item.data(1), item.text(),  str(path), self.customHeaders, "waiting", self.blockNumCard.configItem.value)

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
        self._timer.timeout.connect(self.__progressTextChange)
        self._timer.start(1000)  # 1秒后处理

    def __handleUrl(self, url: str, index: int):
        try:
            _url, fileName, fileSize = getLinkInfo(url, self.customHeaders)
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

    def __progressTextChange(self):
        """ link text changed slot """
        self.threads = []
        
        self.yesButton.setEnabled(False)

        text: list = self.linkTextEdit.toPlainText().split("\n")

        # 获取当前输入的URL列表
        currentUrls = [url.strip() for url in text if url.strip()]
        # 获取之前的URL列表
        previousUrls = [self.taskTableWidget.item(i, 0).data(1) for i in range(self.taskTableWidget.rowCount())]

        # 找出新增、删除和修改的URL
        addedUrls = set(currentUrls) - set(previousUrls)
        removedUrls = set(previousUrls) - set(currentUrls)
        modifiedUrls = set(currentUrls).intersection(set(previousUrls))

        # 删除被删除的URL的行（从后向前遍历）
        for url in removedUrls:
            for i in range(self.taskTableWidget.rowCount() - 1, -1, -1):  # 从后向前遍历
                if self.taskTableWidget.item(i, 0).data(1) == url:
                    self.taskTableWidget.removeRow(i)
                    break

        # 重新生成被编辑过的URL的行
        for url in modifiedUrls:
            for i in range(self.taskTableWidget.rowCount()):
                if self.taskTableWidget.item(i, 0).data(1) == url:
                    item = self.taskTableWidget.item(i, 0)
                    if item.text() != item.data(2):  # 如果用户修改了文件名
                        self.__handleUrl(url, i + 1)  # 重新处理URL
                    break

        # 添加新增的URL的行
        for index, url in enumerate(currentUrls, start=1):
            if url in addedUrls:
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