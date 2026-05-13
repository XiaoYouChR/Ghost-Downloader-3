from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from PySide6.QtCore import QObject, Qt, Signal
from loguru import logger

from app.bases.models import Task
from app.services.core_service import coreService
from app.services.feature_service import featureService
from app.view.components.card_widgets import ParseResultHeaderCardWidget
from app.view.components.cards import ResultCard


@dataclass
class _LineParseState:
    url: str
    callbackId: str = ""
    task: Task | None = None
    resultCard: ResultCard | None = None


class AddTaskParseSession(QObject):
    parsingBusyChanged = Signal(bool)
    parseErrorOccurred = Signal(str, str)
    taskConfirmed = Signal(object)

    def __init__(
        self,
        resultGroup: ParseResultHeaderCardWidget,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._resultGroup = resultGroup
        self._payload: dict[str, Any] = {}
        self._lineStates: list[_LineParseState] = []
        self._activeParses: dict[str, _LineParseState] = {}
        self._acceptedPayloads: dict[str, dict[str, Any]] = {}
        self._payloadOverrides: dict[str, dict[str, Any]] = {}

    def setPayloadOverride(
        self,
        url: str,
        payloadOverride: dict[str, Any],
    ) -> None:
        self._payloadOverrides[url] = payloadOverride

    def setPayload(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        for state in self._lineStates:
            if state.task is None:
                continue
            try:
                state.task.applySettings(self._buildPayload(state.url))
            except Exception as error:
                logger.opt(exception=error).error("同步解析结果设置失败 {}", state.url)

    def canAccept(self) -> bool:
        return any(state.callbackId or state.task is not None for state in self._lineStates)

    def updateUrls(self, currentUrls: list[str]) -> None:
        previousStates = self._lineStates
        previousUrls = [state.url for state in previousStates]
        nextStates: list[_LineParseState] = []
        matcher = SequenceMatcher(a=previousUrls, b=currentUrls, autojunk=False)

        for tag, oldStart, oldEnd, newStart, newEnd in matcher.get_opcodes():
            if tag == "equal":
                nextStates.extend(previousStates[oldStart:oldEnd])
                continue

            for state in previousStates[oldStart:oldEnd]:
                self._clearState(state, cancelRequest=True)

            for url in currentUrls[newStart:newEnd]:
                state = _LineParseState(url=url)
                self._startParse(state)
                nextStates.append(state)

        self._lineStates = nextStates
        self._dropRemovedPayloadOverrides(currentUrls)
        self._syncResultCards()

    def addParsedTasks(self, tasks: list[Task]) -> list[str]:
        if not tasks:
            return []

        stateByUrl = {state.url: state for state in self._lineStates}
        newUrlLines: list[str] = []

        for task in tasks:
            url = task.url
            state = stateByUrl.get(url)
            if state is not None:
                if state.task is not None:
                    continue
                self._clearState(state, cancelRequest=True)
                try:
                    task.applySettings(self._buildPayload(url))
                except Exception as error:
                    logger.opt(exception=error).error("同步解析结果设置失败 {}", url)
                    self._failState(state, self.tr("解析结果处理失败"))
                    continue
                self._setParsedTask(state, task)
                continue

            newUrlLines.append(url)
            state = _LineParseState(url=url)
            try:
                task.applySettings(self._buildPayload(url))
            except Exception as error:
                logger.opt(exception=error).error("同步解析结果设置失败 {}", url)
                self._failState(state, self.tr("解析结果处理失败"))
                self._lineStates.append(state)
                stateByUrl[url] = state
                continue
            self._setParsedTask(state, task)
            self._lineStates.append(state)
            stateByUrl[url] = state

        self._syncResultCards()
        return newUrlLines

    def clear(self) -> None:
        for state in self._lineStates:
            self._clearState(state, cancelRequest=True)

        self._resetSessionState()
        self.parsingBusyChanged.emit(bool(self._activeParses))

    def accept(self) -> list[Task]:
        confirmedTasks: list[Task] = []

        for state in self._lineStates:
            if state.task is not None:
                try:
                    state.task.applySettings(self._buildPayload(state.url))
                    confirmedTasks.append(state.task)
                except Exception as error:
                    logger.opt(exception=error).error("同步已确认任务设置失败 {}", state.url)
                continue

            if not state.callbackId:
                continue

            self._activeParses.pop(state.callbackId, None)
            self._acceptedPayloads[state.callbackId] = self._buildPayload(state.url)

        self.parsingBusyChanged.emit(bool(self._activeParses))

        for state in self._lineStates:
            self._clearState(
                state,
                cancelRequest=state.callbackId not in self._acceptedPayloads,
            )

        self._resetSessionState()
        return confirmedTasks

    def _buildPayload(self, url: str) -> dict[str, Any]:
        payload = self._payload.copy()
        payload.update(self._payloadOverrides.get(url, {}))
        payload["url"] = url
        return payload

    def _startParse(self, state: _LineParseState) -> None:
        callbackId = ""

        def callback(resultTask: Task | None, error: str | None = None) -> None:
            self._onParseFinished(callbackId, resultTask, error)

        try:
            callbackId = coreService.runCoroutine(
                coreService._parse(self._buildPayload(state.url)),
                callback,
            )
        except Exception as error:
            logger.opt(exception=error).error("提交解析请求失败 {}", state.url)
            self.parseErrorOccurred.emit(state.url, str(error))
            return

        state.callbackId = callbackId
        self._activeParses[callbackId] = state
        self.parsingBusyChanged.emit(True)

    def _setParsedTask(self, state: _LineParseState, task: Task) -> None:
        try:
            state.task = task
            state.resultCard = featureService.resultCard(task, self._resultGroup)
        except Exception as error:
            logger.opt(exception=error).error("无法创建解析结果卡片 {}", state.url)
            self._failState(state, self.tr("解析结果处理失败"))

    def _removeResultCard(self, state: _LineParseState) -> None:
        if state.resultCard is None:
            return

        self._resultGroup.scrollLayout.removeWidget(state.resultCard)
        self._resultGroup.updateGeometry()
        state.resultCard.deleteLater()
        state.resultCard = None

    def _clearState(self, state: _LineParseState, cancelRequest: bool) -> None:
        if cancelRequest and state.callbackId:
            self._activeParses.pop(state.callbackId, None)
            coreService.cancelCallback(state.callbackId)
            self.parsingBusyChanged.emit(bool(self._activeParses))

        state.callbackId = ""
        self._removeResultCard(state)
        state.task = None

    def _syncResultCards(self) -> None:
        visibleIndex = 0

        for state in self._lineStates:
            if state.resultCard is None:
                continue

            if self._resultGroup.scrollLayout.indexOf(state.resultCard) != visibleIndex:
                self._resultGroup.scrollLayout.insertWidget(
                    visibleIndex,
                    state.resultCard,
                    alignment=Qt.AlignmentFlag.AlignTop,
                )
            visibleIndex += 1

        self._resultGroup.updateGeometry()

    def _failState(
        self,
        state: _LineParseState,
        errorMessage: str,
    ) -> None:
        state.task = None
        self._removeResultCard(state)
        self.parseErrorOccurred.emit(state.url, errorMessage)

    def _dropRemovedPayloadOverrides(self, urls: list[str]) -> None:
        activeUrls = set(urls)
        self._payloadOverrides = {
            url: payload
            for url, payload in self._payloadOverrides.items()
            if url in activeUrls
        }

    def _resetSessionState(self) -> None:
        self._lineStates.clear()
        self._payloadOverrides.clear()
        self._resultGroup.clearResults()

    def _onParseFinished(
        self,
        callbackId: str,
        resultTask: Task | None,
        error: str | None = None,
    ) -> None:
        state = self._activeParses.pop(callbackId, None)
        if state is not None:
            self.parsingBusyChanged.emit(bool(self._activeParses))
            state.callbackId = ""

            if error or resultTask is None:
                self._failState(state, error or self.tr("解析失败"))
                if error:
                    logger.warning("解析任务失败 {}: {}", state.url, error)
                return

            try:
                resultTask.applySettings(self._buildPayload(state.url))
                self._setParsedTask(state, resultTask)
                self._syncResultCards()
            except Exception as error:
                logger.opt(exception=error).error("无法创建解析结果卡片 {}", state.url)
                self._failState(state, self.tr("解析结果处理失败"))
            return

        acceptedPayload = self._acceptedPayloads.pop(callbackId, None)
        if acceptedPayload is None:
            return

        if error or resultTask is None:
            if error:
                logger.warning("后台确认任务解析失败: {}", error)
            return

        try:
            resultTask.applySettings(acceptedPayload)
            self.taskConfirmed.emit(resultTask)
        except Exception as error:
            logger.opt(exception=error).error(
                "无法创建任务卡片 {}", getattr(resultTask, "title", "Unknown")
            )
