from typing import Any, Self

from PySide6.QtCore import QEvent, Qt, QPoint, QTimer
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import QDialog
from loguru import logger
from qfluentwidgets import (
    MessageBoxBase,
    SubtitleLabel,
    LineEdit,
    Action,
    FluentIcon,
    PlainTextEdit,
)

from app.bases.models import Task
from app.services.core_service import coreService
from app.services.feature_service import featureService
from app.supports.config import DEFAULT_HEADERS
from app.supports.utils import getProxies
from app.view.components.card_widgets import (
    ParseResultHeaderCardWidget,
    SettingHeaderCardWidget,
)


class AddTaskDialog(MessageBoxBase):

    instance: Self = None

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
        # for i in range(5):
        #     self.parseResultGroup.addWidget(
        #         HttpResultCard(
        #             HttpTask(
        #                 title=f"DingTalk-{i}.avi",
        #                 fileSize=123456789,
        #                 url="https://example.com/DingTalk.exe",
        #             ),
        #             self.parseResultGroup,
        #         )
        #     )

    def initWidget(self):
        self.setObjectName("AddTaskDialog")
        self.widget.setFixedWidth(700)

        self.urlEdit.setPlaceholderText(
            self.tr("添加多个下载链接时，请确保每行只有一个下载链接")
        )
        self.urlEdit.setWordWrapMode(QTextOption.WrapMode.NoWrap)

        self.pathEdit.addAction(self.selectFolderAction)
        self.settingGroup.addGroup(
            FluentIcon.DOWNLOAD, self.tr("选择下载路径"), self.pathEdit, 2
        )
        for card in featureService.getDialogCards(self.settingGroup):
            self.settingGroup.addWidget(card)

    def initLayout(self):
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.urlEdit)
        self.viewLayout.addWidget(self.parseResultGroup)
        self.viewLayout.addWidget(self.settingGroup)

    def connectSignalToSlot(self):
        self._timer.timeout.connect(self.parse)
        self.urlEdit.textChanged.connect(
            lambda: (self._timer.stop(), self._timer.start(1000))
        )

    def parse(self):
        """解析输入的URL列表"""
        urls = self.urlEdit.toPlainText().strip().split("\n")
        headers = DEFAULT_HEADERS
        proxies = getProxies()

        self.parseResultGroup.clearResults()

        for url in urls:
            url = url.strip()
            if url:  # 跳过空行
                payload = {"url": url, "headers": headers, "proxies": proxies}
                try:
                    coreService.parseUrl(payload, self._handleParseResult)
                except Exception as e:
                    logger.error(f"提交解析请求失败: {repr(e)}")

    def _handleParseResult(self, resultTask: Task, error: str = None):
        """处理 URL 解析结果的回调函数

        Args:
            resultTask: 解析成功时的结果
            error: 解析失败时的错误信息
        """
        if error:
            logger.error(error)
            return

        if resultTask:
            try:
                resultCard = featureService.createResultCard(resultTask, self.parseResultGroup)
                self.parseResultGroup.addWidget(resultCard)
            except Exception as e:
                logger.error(f"无法创建解析结果卡片: {repr(e)}")

    def done(self, code):
        if code == QDialog.DialogCode.Rejected:
            self.urlEdit.clear()
            self.parseResultGroup.clearResults()

        # Accept 情况由 MainWindow 处理

        super().done(code)

    @classmethod
    def display(cls, payload: dict[str, Any] = None, parent=None):
        if cls.instance is None:
            cls.instance = cls(parent)

        return cls.instance.exec()

    def eventFilter(self, obj, e: QEvent):
        if obj is self.windowMask:
            if (
                e.type() == QEvent.Type.MouseButtonPress
                and e.button() == Qt.MouseButton.LeftButton
            ):
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
