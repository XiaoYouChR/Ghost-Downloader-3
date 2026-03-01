from typing import Any

from PySide6.QtCore import QEvent, Qt, QPoint, QTimer
from PySide6.QtGui import QTextOption
from qfluentwidgets import MessageBoxBase, SubtitleLabel, LineEdit, Action, FluentIcon, GroupHeaderCardWidget, \
    PlainTextEdit

from app.services.core_service import coreService
from app.supports.config import cfg, DEFAULT_HEADERS
from app.supports.utils import getProxies
from app.view.components.card_widgets import ParseResultHeaderCardWidget, SettingHeaderCardWidget
from app.view.components.cards import ResultCardBase


class AddTaskDialog(MessageBoxBase):

    _instance = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(self.tr("添加任务"), self)
        self.urlEdit = PlainTextEdit(self)
        self.parseResultGroup = ParseResultHeaderCardWidget(self)
        self.settingGroup = SettingHeaderCardWidget(self)
        self.pathEdit = LineEdit(self)
        self.selectFolderAction = Action(FluentIcon.FOLDER, self.tr("选择文件夹"), self)

        self._timer = QTimer(self, singleShot=True)

        self.initWidget()
        self.initLayout()
        self.connectSignalToSlot()

        # TODO For Test
        # self.parseResultGroup.hide()
        for i in range(5):
            self.parseResultGroup.addWidget(
                ResultCardBase(f"DingTalk-{i}.avi", 123456789, "https://example.com/DingTalk.exe", self.parseResultGroup))

    def initWidget(self):
        self.setObjectName("AddTaskDialog")
        self.widget.setFixedWidth(700)

        self.urlEdit.setPlaceholderText(self.tr("添加多个下载链接时，请确保每行只有一个下载链接"))
        self.urlEdit.setWordWrapMode(QTextOption.WrapMode.NoWrap)

        self.pathEdit.addAction(self.selectFolderAction)
        self.settingGroup.addGroup(FluentIcon.DOWNLOAD, self.tr("选择下载路径"), self.pathEdit, 2)

    def initLayout(self):
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.urlEdit)
        self.viewLayout.addWidget(self.parseResultGroup)
        self.viewLayout.addWidget(self.settingGroup)

    def connectSignalToSlot(self):
        self._timer.timeout.connect(self.parse)
        self.pathEdit.textChanged.connect(lambda: (self._timer.stop(), self._timer.start(1000)))

    def parse(self):
        """解析输入的URL列表"""
        urls = self.urlEdit.toPlainText().strip().split("\n")
        headers = DEFAULT_HEADERS
        proxies = getProxies()
        
        # 清空之前的解析结果
        self.parseResultGroup.clearResults()
        
        for url in urls:
            url = url.strip()
            if url:  # 跳过空行
                payload = {
                    "url": url,
                    "headers": headers,
                    "proxies": proxies
                }
                # 使用回调函数处理解析结果
                try:
                    coreService.parseUrl(payload, self._handleParseResult)
                except Exception as e:
                    print(f"提交解析请求失败: {e}")
    
    def _handleParseResult(self, result: dict, error: str = None):
        """处理 URL 解析结果的回调函数
        
        Args:
            result: 解析成功时的结果字典
            error: 解析失败时的错误信息
        """
        if error:
            # 处理解析错误
            print(f"解析失败: {error}")
            # TODO: 显示错误信息给用户
            return
        
        if result:
            # 提取解析结果
            filename = result.get('filename', '未知文件')
            file_size = result.get('fileSize', 0)
            url = result.get('url', '')
            
            # 添加到界面
            self.addParseResult(filename, file_size, url)

    def addParseResult(self, filename: str, fileSize: int, url: str):
        """添加解析结果卡片到滚动区域
        
        Args:
            filename: 文件名
            fileSize: 文件大小
            url: 下载链接
        
        Returns:
            ResultCardBase: 创建的结果卡片对象
        """
        try:
            resultCard = ResultCardBase(filename, fileSize, url, self.parseResultGroup)
            self.parseResultGroup.addWidget(resultCard)
            return resultCard
        except Exception as e:
            print(f"添加解析结果失败: {e}")
            return None

    def done(self, code):
        ...
        super().done(code)

    @classmethod
    def display(cls, payload: dict[str, Any]=None, parent=None):
        if cls._instance is None:
            cls._instance = cls(parent)

        cls._instance.exec()

    def closeEvent(self, e):
        self.urlEdit.clear()
        self.parseResultGroup.clearResults()
        return super().closeEvent(e)

    def eventFilter(self, obj, e: QEvent):
        if obj is self.windowMask:
            if e.type() == QEvent.Type.MouseButtonPress and e.button() == Qt.MouseButton.LeftButton:
                self._dragPos = e.pos()
                return True
            elif e.type() == QEvent.Type.MouseMove and not self._dragPos.isNull():
                pos = self.window().pos() + e.pos() - self._dragPos
                pos.setX(max(0, pos.x()))
                pos.setY(max(0, pos.y()))

                self.window().move(pos)
                return True
            elif e.type() == QEvent.Type.MouseButtonRelease:
                self._dragPos = QPoint()

        return super().eventFilter(obj, e)
