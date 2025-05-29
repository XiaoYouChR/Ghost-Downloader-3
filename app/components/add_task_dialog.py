import os
import re
from pathlib import Path
from threading import Thread

from PySide6.QtCore import Signal, Qt, QTimer, QEvent
from PySide6.QtGui import QColor, QResizeEvent
from PySide6.QtWidgets import QTableWidgetItem
from qfluentwidgets import PushSettingCard, RangeSettingCard, MessageBox, InfoBar, InfoBarPosition, FluentStyleSheet
from qfluentwidgets.common.icon import FluentIcon as FIF

from app.components.custom_mask_dialog_base import MaskDialogBase
from .Ui_AddTaskOptionDialog import Ui_AddTaskOptionDialog
from .custom_dialogs import EditHeadersDialog
from .select_folder_setting_card import SelectFolderSettingCard
from ..common.config import cfg, Headers
from ..common.methods import getReadableSize, getLinkInfo, addDownloadTask

URL_REGEX = re.compile(r"^" +  # Renamed
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
    
    _instance = None  # type: 'AddTaskOptionDialog' # Kept as is, conventional for singleton-like patterns
    _isInitialized: bool = False  # Renamed
    _addTableRowSignal = Signal(str, str, str)  # Renamed
    _gotWrongSignal = Signal(str, int) # Renamed


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
        self.downloadFolderCard = SelectFolderSettingCard(cfg.downloadFolder, cfg.historyDownloadFolder, self.widget)

        self.blockNumCard = RangeSettingCard(
            cfg.preBlockNum,
            FIF.CLOUD,
            self.tr("下载线程数"),
            '',
            self.widget
        )

        # Edit customHeaders Card
        self.editHeadersCard = PushSettingCard(
            self.tr("编辑请求标头"),
            FIF.EDIT,
            self.tr("自定义请求标头"),
            "",
            self.widget
        )

        self.verticalLayout.insertWidget(4, self.downloadFolderCard)
        self.verticalLayout.insertWidget(5, self.blockNumCard)
        self.verticalLayout.insertWidget(6, self.editHeadersCard)

        self._connectSignalToSlot() # Renamed

    def eventFilter(self, obj, e: QEvent):
        if obj is self.window():
            if e.type() == QEvent.Resize:
                re = QResizeEvent(e)
                self.resize(re.size())
        elif obj is self.windowMask:
            if e.type() == QEvent.MouseButtonRelease and e.button() == Qt.LeftButton \
                    and self.isClosableOnMaskClicked():
                self.close()

        return super().eventFilter(obj, e)

    @classmethod
    def showAddTaskOptionDialog(cls, urlContent:str = "", parent:"QWidget"= None, headers:dict = None):
        if cls._isInitialized: # Renamed
            _ = cls._instance.linkTextEdit.toPlainText()
            if urlContent and not urlContent in _.split('\n'):
                _ += "\n" + urlContent
                cls._instance.linkTextEdit.setPlainText(_)
        else:
            cls._instance = AddTaskOptionDialog(parent=parent)
            cls._isInitialized = True # Renamed
            cls._instance.linkTextEdit.setPlainText(urlContent)

        if headers: 
            cls._instance.customHeaders = headers

        cls._instance.exec()

    def closeEvent(self, event):
        self._whenClosed() # Renamed
        super().closeEvent(event)
        self.deleteLater()

    @classmethod
    def _whenClosed(cls): # Renamed
        cls._isInitialized = False # Renamed
        cls._instance = None

    def _connectSignalToSlot(self): # Renamed
        # self.downloadFolderCard.clicked.connect(self._onDownloadFolderCardClicked) # Removed

        self.noButton.clicked.connect(self.close)
        self.yesButton.clicked.connect(self._onYesButtonClicked) # Renamed
        self.laterAction.triggered.connect(self._onLaterActionTriggered) # Renamed
        self.taskTableWidget.itemChanged.connect(self._onTaskTableWidgetItemChanged) # Renamed
        self.linkTextEdit.textChanged.connect(self._onLinkTextChanged) # Renamed
        self._addTableRowSignal.connect(self._addTableRow) # Renamed
        self._gotWrongSignal.connect(self._handleWrong) # Renamed
        self.editHeadersCard.clicked.connect(self._onEditHeadersCardClicked) # Renamed

    def _handleWrong(self, error: str, index: int): # Renamed
        InfoBar.error(
            title=self.tr('错误'),
            content=self.tr("解析第 {} 个链接时遇到错误: {}").format(index, error),
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=10000,
            parent=self.parent()
        )

    def _onEditHeadersCardClicked(self): # Renamed
        newHeaders, ok = EditHeadersDialog(self, initialHeaders=self.customHeaders).getHeaders()
        if newHeaders and ok:
            self.customHeaders = newHeaders

    def _onYesButtonClicked(self): # Renamed
        path = Path(self.downloadFolderCard.contentLabel.text())

        # 检测路径是否有权限写入
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                MessageBox(self.tr("错误"), repr(e), self)
        else:
            if not os.access(path, os.W_OK):
                MessageBox(self.tr("错误"), self.tr("似乎是没有权限向此目录写入文件"), self)

        for i in range(self.taskTableWidget.rowCount()):
            item = self.taskTableWidget.item(i, 0)
            # Pass item.text() directly. If empty, DefaultDownloadTask will derive it.
            # item.data(2) holds the original filename detected by getLinkInfo.
            fileName = item.text() 

            addDownloadTask(item.data(1), fileName, str(path), self.customHeaders, preBlockNum=self.blockNumCard.configItem.value)

        self.close()

    def _onLaterActionTriggered(self): # Renamed
        path = Path(self.downloadFolderCard.contentLabel.text())

        # 检测路径是否有权限写入
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                MessageBox(self.tr("错误"), repr(e), self)
        else:
            if not os.access(path, os.W_OK):
                MessageBox(self.tr("错误"), self.tr("似乎是没有权限向此目录写入文件"), self)

        for i in range(self.taskTableWidget.rowCount()):
            item = self.taskTableWidget.item(i, 0)
            # Pass item.text() directly. If empty, DefaultDownloadTask will derive it.
            fileName = item.text()

            addDownloadTask(item.data(1), fileName, str(path), self.customHeaders, "paused", self.blockNumCard.configItem.value)

        self.close()

    # This method seems unused after removing the direct connect, SelectFolderSettingCard handles its own logic
    # def _onDownloadFolderCardClicked(self): 
    #     """ download folder card clicked slot """
    #     folder = QFileDialog.getExistingDirectory(
    #         self, self.tr("选择文件夹"), "./")
    #     if not folder or self.downloadFolderCard.contentLabel.text() == folder:
    #         return
    #     self.downloadFolderCard.setContent(folder)

    def _onLinkTextChanged(self): # Renamed
        if hasattr(self, '_timer'):
            self._timer.stop()

        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._progressTextChange) # Renamed
        self._timer.start(1000)  # 1秒后处理

    def _handleUrl(self, url: str, index: int): # Renamed
        try:
            _url, fileName, fileSize = getLinkInfo(url, self.customHeaders)
            # 查找是否存在该 URL 的行
            for i in range(self.taskTableWidget.rowCount()):
                if self.taskTableWidget.item(i, 0).data(1) == url:
                    # 更新文件名和文件大小
                    self.taskTableWidget.item(i, 0).setText(fileName)
                    self.taskTableWidget.item(i, 1).setText(getReadableSize(int(fileSize)))
                    return
            # 如果不存在则添加新行
            self._addTableRowSignal.emit(fileName, str(fileSize), url) # Renamed
        except Exception as e:
            self._gotWrongSignal.emit(repr(e), index) # Renamed

    def _addTableRow(self, fileName: str, fileSize: str, url: str): # Renamed
        """ add table row slot """
        self.taskTableWidget.insertRow(self.taskTableWidget.rowCount())
        _ = QTableWidgetItem(fileName)
        _.setData(1, url) # 记录 Url
        _.setData(2, fileName) # 设置默认值, 当用户修改后的内容为空是，使用默认值替换
        self.taskTableWidget.setItem(self.taskTableWidget.rowCount() - 1, 0, _)
        _ = QTableWidgetItem(getReadableSize(int(fileSize)))
        _.setFlags(Qt.ItemIsEnabled)  # 禁止编辑
        self.taskTableWidget.setItem(self.taskTableWidget.rowCount() - 1, 1, _)

        # self.taskTableWidget.resizeColumnsToContents() # This can be uncommented if desired

    def _onTaskTableWidgetItemChanged(self, item: QTableWidgetItem): # Renamed
        """ task table widget item changed slot """
        if item.text() == '':
            item.setText(item.data(2))

    def _progressTextChange(self): # Renamed
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
                        self._handleUrl(url, i + 1)  # Renamed # 重新处理URL
                    break

        # 添加新增的URL的行
        for index, url in enumerate(currentUrls, start=1):
            if url in addedUrls:
                _ = URL_REGEX.search(url) # Renamed
                if _:
                    self._addTableRow(url, "0", url)  # Renamed # 新增卡片并设置文件名和文件大小为“正在获取...”
                    self.threads.append(Thread(target=self._handleUrl, args=(url, index), daemon=True)) # Renamed
                else:
                    InfoBar.warning(
                        title=self.tr('警告'),
                        content=self.tr("第{}个链接无效!").format(index),
                        orient=Qt.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP,
                        duration=1000,
                        parent=self.parent()
                    )

        self.yesButton.setEnabled(True)

        if self.threads:
            for thread in self.threads:
                thread.start()

            Thread(target=self._waitForThreads, daemon=True).start() # Renamed
    
    def _waitForThreads(self): # Renamed
        for thread in self.threads:
            thread.join()
