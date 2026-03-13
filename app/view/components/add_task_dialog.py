from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Self

from PySide6.QtCore import QEvent, Qt, QPoint, QTimer, Signal, QSize
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import QDialog, QFileDialog, QSizePolicy
from loguru import logger
from qfluentwidgets import (
    MessageBoxBase,
    SubtitleLabel,
    LineEdit,
    Action,
    FluentIcon,
    PlainTextEdit,
    InfoBar,
    InfoBarPosition,
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
from app.view.components.cards import ParseSettingCard, ResultCard


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


@dataclass
class _LineParseState:
    url: str
    requestId: int = 0
    callbackId: str = ""
    status: str = "idle"
    task: Task | None = None
    resultCard: ResultCard | None = None


@dataclass
class _AcceptedPendingParse:
    payload: dict[str, Any]


class AutoSizingEdit(PlainTextEdit):
    def __init__(self, parent=None, minimumVisibleLines: int = 5):
        super().__init__(parent)
        self._minimumVisibleLines = minimumVisibleLines
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.document().blockCountChanged.connect(self.updateGeometry)

    def _lineHeight(self) -> int:
        return self.fontMetrics().lineSpacing()

    def _editorChromeHeight(self) -> int:
        margins = self.contentsMargins()
        viewportMargins = self.viewportMargins()
        documentMargin = round(self.document().documentMargin() * 2)
        return (
            margins.top()
            + margins.bottom()
            + viewportMargins.top()
            + viewportMargins.bottom()
            + self.frameWidth() * 2
            + documentMargin
        )

    def _sizeHintForLineCount(self, lineCount: int) -> QSize:
        size = super().sizeHint()
        height = self._editorChromeHeight() + self._lineHeight() * lineCount
        return QSize(size.width(), height)

    def minimumSizeHint(self) -> QSize:
        return self._sizeHintForLineCount(min(self._minimumVisibleLines, self.document().blockCount()))

    def maximumSizeHint(self) -> QSize:
        return self._sizeHintForLineCount(self.document().blockCount())

    def sizeHint(self) -> QSize:
        return self.maximumSizeHint().expandedTo(self.minimumSizeHint())


class AddTaskDialog(MessageBoxBase):
    taskConfirmed = Signal(object)

    instance: Self = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(self.tr("添加任务"), self)
        self.urlEdit = AutoSizingEdit(self)
        self.parseResultGroup = ParseResultHeaderCardWidget(self)
        self.settingGroup = ParseSettingHeaderCardWidget(self)
        self.selectFolderCard = SelectFolderCard(FluentIcon.DOWNLOAD, self.tr('选择下载路径'), self)

        self._timer = QTimer(self, singleShot=True)
        self._lineStates: list[_LineParseState] = []
        self._activeRequests: dict[int, _LineParseState] = {}
        self._acceptedPendingParses: dict[int, _AcceptedPendingParse] = {}
        self._confirmedTasks: list[Task] = []
        self._payloadOverrides: dict[str, dict[str, Any]] = {}  # TODO, 这是一种临时解决方案, 最佳方案是让 ResultCard 可以自定义 Payload
        self._requestSerial = 0

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
        """按行同步解析输入的 URL 列表"""
        currentUrls = self._getEditorUrls()
        previousStates = self._lineStates
        previousUrls = [state.url for state in previousStates]
        nextStates: list[_LineParseState] = []
        matcher = SequenceMatcher(a=previousUrls, b=currentUrls, autojunk=False)

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                nextStates.extend(previousStates[i1:i2])
                continue

            for state in previousStates[i1:i2]:
                self._disposeLineState(state, cancelRequest=True)

            for url in currentUrls[j1:j2]:
                state = _LineParseState(url=url)
                self._submitParse(state)
                nextStates.append(state)

        self._lineStates = nextStates
        self._rebuildResultCards()

    def _getEditorUrls(self) -> list[str]:
        text = self.urlEdit.toPlainText()
        if not text:
            return []
        return [line.strip() for line in text.splitlines() if line.strip()]

    def appendUrls(self, urls: list[str]):
        if not urls:
            return

        self.urlEdit.appendPlainText("\n".join(urls))
        self._timer.stop()
        self.parse()

    def appendUrlWithPayload(self, url: str, payloadOverride: dict[str, Any]):
        self._payloadOverrides[url] = payloadOverride
        self.appendUrls([url])

    def getPayload(self, url) -> dict[str, Any]:
        payload = self.getCurrentPayload()
        payload.update(self._payloadOverrides.get(url, {}))
        payload["url"] = url
        return payload

    def getCurrentPayload(self) -> dict[str, Any]:
        payload = {
            "headers": DEFAULT_HEADERS.copy(),
            "proxies": getProxies(),
        }
        payload.update(self.settingGroup.payload)
        return payload

    def _applyCurrentPayloadToTask(self, task: Task):
        payload = self.getCurrentPayload()
        task.applyPayloadToTask(payload)

    def syncPayload(self):
        for state in self._lineStates:
            if state.task is None:
                continue
            try:
                self._applyCurrentPayloadToTask(state.task)
            except Exception as e:
                logger.opt(exception=e).error("同步解析结果设置失败 {}", state.url)

    def _submitParse(self, state: _LineParseState):
        self._requestSerial += 1
        requestId = self._requestSerial

        state.requestId = requestId
        state.status = "pending"
        state.task = None
        self._activeRequests[requestId] = state

        try:
            state.callbackId = coreService.parseUrl(
                self.getPayload(state.url),
                lambda resultTask, error=None, requestId=requestId: self._handleParseResult(
                    requestId, resultTask, error
                ),
            )
        except Exception as e:
            self._activeRequests.pop(requestId, None)
            state.callbackId = ""
            state.status = "error"
            logger.opt(exception=e).error("提交解析请求失败 {}", state.url)
            self._showParseError(state.url, str(e))

    def _removeResultCard(self, state: _LineParseState):
        if state.resultCard is None:
            return

        self.parseResultGroup.scrollLayout.removeWidget(state.resultCard)
        self.parseResultGroup.updateGeometry()
        state.resultCard.deleteLater()
        state.resultCard = None

    def _disposeLineState(self, state: _LineParseState, cancelRequest: bool):
        if cancelRequest and state.requestId:
            self._activeRequests.pop(state.requestId, None)
            if state.callbackId:
                coreService.removeCallback(state.callbackId)

        self._payloadOverrides.pop(state.url, None)
        state.callbackId = ""
        self._removeResultCard(state)
        state.task = None
        state.status = "idle" if state.url else "empty"

    def _rebuildResultCards(self):
        visibleIndex = 0

        for state in self._lineStates:
            if state.resultCard is None:
                continue

            if self.parseResultGroup.scrollLayout.indexOf(state.resultCard) != visibleIndex:
                self.parseResultGroup.scrollLayout.insertWidget(
                    visibleIndex,
                    state.resultCard,
                    alignment=Qt.AlignmentFlag.AlignTop,
                )
            visibleIndex += 1

        self.parseResultGroup.updateGeometry()

    def _showParseError(self, url: str, error: str | None = None):
        displayUrl = url if len(url) <= 48 else f"{url[:45]}..."

        content = self.tr("{0}\n{1}").format(displayUrl, error)

        InfoBar.error(
            self.tr("链接解析失败"),
            content,
            duration=5000,
            position=InfoBarPosition.BOTTOM_RIGHT,
            parent=self,
        )

    def _handleParseResult(self, requestId: int, resultTask: Task, error: str = None):
        state = self._activeRequests.pop(requestId, None)
        if state is not None:
            state.callbackId = ""

            if error or resultTask is None:
                state.status = "error"
                state.task = None
                self._removeResultCard(state)
                self._showParseError(state.url, error or self.tr("解析失败"))
                if error:
                    logger.warning("解析任务失败 {}: {}", state.url, error)
                return

            try:
                self._applyCurrentPayloadToTask(resultTask)
                state.task = resultTask
                state.status = "success"
                if state.resultCard is None:
                    state.resultCard = featureService.createResultCard(
                        resultTask, self.parseResultGroup
                    )
                self._rebuildResultCards()
            except Exception as e:
                state.status = "error"
                state.task = None
                self._removeResultCard(state)
                logger.opt(exception=e).error("无法创建解析结果卡片 {}", state.url)
                self._showParseError(state.url, self.tr("解析结果处理失败"))
            return

        acceptedParse = self._acceptedPendingParses.pop(requestId, None)
        if acceptedParse is None:
            return

        if error or resultTask is None:
            if error:
                logger.warning("后台确认任务解析失败: {}", error)
            return

        try:
            resultTask.applyPayloadToTask(acceptedParse.payload)
            self.taskConfirmed.emit(resultTask)
        except Exception as e:
            logger.opt(exception=e).error("无法创建任务卡片 {}", getattr(resultTask, "title", "Unknown"))

    def _clearEditorState(self):
        self._timer.stop()
        for state in self._lineStates:
            self._disposeLineState(state, cancelRequest=True)
        self._lineStates.clear()
        self.parseResultGroup.clearResults()

        self.urlEdit.blockSignals(True)
        self.urlEdit.clear()
        self.urlEdit.blockSignals(False)

    def _commitAcceptedTasks(self):
        self._confirmedTasks.clear()
        acceptedPayload = self.getCurrentPayload()

        for state in self._lineStates:
            if state.status == "success" and state.task is not None:
                try:
                    state.task.applyPayloadToTask(acceptedPayload)
                    self._confirmedTasks.append(state.task)
                except Exception as e:
                    logger.opt(exception=e).error("同步已确认任务设置失败 {}", state.url)
            elif state.status == "pending" and state.requestId:
                self._activeRequests.pop(state.requestId, None)
                self._acceptedPendingParses[state.requestId] = _AcceptedPendingParse(
                    payload=acceptedPayload,
                )
                state.callbackId = ""

        self._timer.stop()
        for state in self._lineStates:
            keepPendingRequest = (
                state.status == "pending" and state.requestId in self._acceptedPendingParses
            )
            self._disposeLineState(state, cancelRequest=not keepPendingRequest)
        self._lineStates.clear()
        self.parseResultGroup.clearResults()

        self.urlEdit.blockSignals(True)
        self.urlEdit.clear()
        self.urlEdit.blockSignals(False)

    def takeConfirmedTasks(self) -> list[Task]:
        tasks = self._confirmedTasks.copy()
        self._confirmedTasks.clear()
        return tasks

    def done(self, code):
        if code == QDialog.DialogCode.Rejected:
            self._confirmedTasks.clear()
            self._clearEditorState()
        elif code == QDialog.DialogCode.Accepted:
            self._commitAcceptedTasks()

        super().done(code)

    def validate(self) -> bool:
        self._timer.stop()
        self.parse()

        return any(state.status in {"pending", "success"} for state in self._lineStates)

    @classmethod
    def initialize(cls, parent=None):
        if cls.instance is None:
            cls.instance = cls(parent)

        return cls.instance

    def eventFilter(self, obj, e: QEvent):
        if obj is self.windowMask:
            if (
                e.type() == QEvent.Type.MouseButtonPress
                and e.button() == Qt.MouseButton.LeftButton
            ):
                self._dragPos = e.pos()
                return True
            elif e.type() == QEvent.Type.MouseMove and not self._dragPos.isNull():
                window = self.window()
                if window.isMaximized():
                    window.showNormal()

                pos = window.pos() + e.pos() - self._dragPos
                pos.setX(max(0, pos.x()))
                pos.setY(max(0, pos.y()))

                window.move(pos)
                return True
            elif e.type() == QEvent.Type.MouseButtonRelease:
                self._dragPos = QPoint()

        return super().eventFilter(obj, e)
