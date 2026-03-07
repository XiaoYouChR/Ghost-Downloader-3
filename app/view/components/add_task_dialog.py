from pathlib import Path
from typing import Any, Self

from PySide6.QtCore import QEvent, Qt, QPoint, QTimer
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import QDialog, QFileDialog
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
from app.supports.config import DEFAULT_HEADERS, cfg
from app.supports.utils import getProxies
from app.view.components.card_widgets import (
    ParseResultHeaderCardWidget,
    ParseSettingHeaderCardWidget,
)
from app.view.components.cards import ParseSettingCard


class SelectFolderCard(ParseSettingCard):
    def initCustomWidget(self):
        # init widget
        self.pathEdit = LineEdit(self)
        self.selectFolderAction = Action(FluentIcon.FOLDER, self.tr("选择文件夹"), self)
        self.selectFolderAction.triggered.connect(self._selectFolder)
        self.pathEdit.addAction(self.selectFolderAction)
        self.pathEdit.setReadOnly(True)
        self.pathEdit.setText(cfg.downloadFolder.value)
        # init layout
        self.hBoxLayout.addWidget(self.pathEdit, stretch=3)

    def _selectFolder(self):
        path = Path(self.pathEdit.text())
        if path.exists():
            path = path.absolute()
        else:
            path = path.parent

        path = QFileDialog.getExistingDirectory(
            self, self.tr("选择下载路径"), str(path)
        )
        if path:
            self.pathEdit.setText(path)
            self.payloadChanged.emit()

    @property
    def payload(self) -> dict[str, Any]:
        return {"path": Path(self.pathEdit.text())}

class AddTaskDialog(MessageBoxBase):

    instance: Self = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(self.tr("添加任务"), self)
        self.urlEdit = PlainTextEdit(self)
        self.parseResultGroup = ParseResultHeaderCardWidget(self)
        self.settingGroup = ParseSettingHeaderCardWidget(self)
        self.selectFolderCard = SelectFolderCard(FluentIcon.DOWNLOAD, self.tr('选择下载路径'), self)

        self._timer = QTimer(self, singleShot=True)

        self.initWidget()
        self.initLayout()
        self.connectSignalToSlot()

    def initWidget(self):
        self.setObjectName("AddTaskDialog")
        self.widget.setFixedWidth(700)

        self.urlEdit.setPlaceholderText(
            self.tr("添加多个下载链接时，请确保每行只有一个下载链接")
        )
        self.urlEdit.setWordWrapMode(QTextOption.WrapMode.NoWrap)

        self.settingGroup.addCard(self.selectFolderCard)
        for card in featureService.getDialogCards(self.settingGroup):
            self.settingGroup.addCard(card)
            card.payloadChanged.connect(self.syncPayload)

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

        self.parseResultGroup.clearResults()

        for url in urls:
            url = url.strip()
            if url:
                try:
                    coreService.parseUrl(self.getPayload(url), self._handleParseResult)
                except Exception as e:
                    logger.error(f"提交解析请求失败: {repr(e)}")

    def getPayload(self, url) -> dict[str, Any]:
        payload = self.getCurrentPayload()
        payload["url"] = url
        return payload

    def getCurrentPayload(self) -> dict[str, Any]:
        payload = {
            "headers": DEFAULT_HEADERS.copy(),
            "proxies": getProxies(),
        }
        payload.update(self.settingGroup.payload)
        print(payload)
        return payload

    def _applyCurrentPayloadToTask(self, task: Task):
        payload = self.getCurrentPayload()
        task.applyPayloadToTask(payload)

    def syncPayload(self):
        for task in self.parseResultGroup.getAllTasks():
            try:
                self._applyCurrentPayloadToTask(task)
            except Exception as e:
                logger.error(f"同步解析结果设置失败: {repr(e)}")

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
                self._applyCurrentPayloadToTask(resultTask)
                resultCard = featureService.createResultCard(resultTask, self.parseResultGroup)
                self.parseResultGroup.addWidget(resultCard)
            except Exception as e:
                logger.error(f"无法创建解析结果卡片: {repr(e)}")

    def done(self, code):
        if code == QDialog.DialogCode.Rejected:
            self.urlEdit.clear()
            self.parseResultGroup.clearResults()
        elif code == QDialog.DialogCode.Accepted:
            self.syncPayload()

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
