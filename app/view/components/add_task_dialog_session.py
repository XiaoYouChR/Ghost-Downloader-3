from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal
from loguru import logger

from app.bases.models import Task
from app.services.category_service import categoryService
from app.services.core_service import coreService


@dataclass
class _LineParseState:
    url: str
    callbackId: str = ""
    task: Task | None = None


class AddTaskParseSession(QObject):
    # 纯 state + 异步 parse 编排, 不持 widget 引用; ResultCard 生命周期由 AddTaskDialog
    # 通过下面这一组信号驱动

    parsingBusyChanged = Signal(bool)
    parseSucceeded = Signal(str, object)    # (url, task)
    parseFailed = Signal(str, str)          # (url, errorMessage)
    lineRemoved = Signal(str)               # (url)
    linesReordered = Signal()
    cleared = Signal()
    taskConfirmed = Signal(object)          # 用户已 accept 但 parse 这时才回来的 task

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._payload: dict[str, Any] = {}
        self._lineStates: list[_LineParseState] = []
        self._activeParses: dict[str, _LineParseState] = {}
        self._acceptedPayloads: dict[str, dict[str, Any]] = {}
        self._payloadOverrides: dict[str, dict[str, Any]] = {}

    def urls(self) -> list[str]:
        return [state.url for state in self._lineStates]

    def taskByUrl(self, url: str) -> Task | None:
        for state in self._lineStates:
            if state.url == url:
                return state.task
        return None

    def canAccept(self) -> bool:
        return any(state.callbackId or state.task is not None for state in self._lineStates)

    def setPayload(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        for state in self._lineStates:
            if state.task is None:
                continue
            state.task.applySettings(self._buildPayload(state.url))

    def setUrlCategoryOverride(self, url: str, categoryId: str) -> None:
        self._payloadOverrides[url] = {"category": categoryId}

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
                self._dropState(state, cancelRequest=True)

            for url in currentUrls[newStart:newEnd]:
                state = _LineParseState(url=url)
                self._submitParse(state)
                nextStates.append(state)

        self._lineStates = nextStates
        activeUrls = set(currentUrls)
        self._payloadOverrides = {
            url: payload for url, payload in self._payloadOverrides.items() if url in activeUrls
        }
        self.linesReordered.emit()

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
                self._dropState(state, cancelRequest=True)
            else:
                newUrlLines.append(url)
                state = _LineParseState(url=url)
                self._lineStates.append(state)
                stateByUrl[url] = state

            task.applySettings(self._buildPayload(url))
            state.task = task
            self.parseSucceeded.emit(url, task)

        self.linesReordered.emit()
        return newUrlLines

    def clear(self) -> None:
        for state in self._lineStates:
            self._dropState(state, cancelRequest=True, silent=True)
        self._lineStates.clear()
        self._payloadOverrides.clear()
        self.cleared.emit()
        self.parsingBusyChanged.emit(bool(self._activeParses))

    def accept(self) -> list[Task]:
        confirmedTasks: list[Task] = []

        for state in self._lineStates:
            if state.task is not None:
                state.task.applySettings(self._buildPayload(state.url))
                confirmedTasks.append(state.task)
                continue

            if not state.callbackId:
                continue

            self._activeParses.pop(state.callbackId, None)
            self._acceptedPayloads[state.callbackId] = self._buildPayload(state.url)

        self.parsingBusyChanged.emit(bool(self._activeParses))

        for state in self._lineStates:
            if state.callbackId and state.callbackId not in self._acceptedPayloads:
                coreService.cancelCallback(state.callbackId)

        self._lineStates.clear()
        self._payloadOverrides.clear()
        self.cleared.emit()
        return confirmedTasks

    def replaceUrl(self, oldUrl: str, newUrl: str) -> None:
        for state in self._lineStates:
            if state.url == oldUrl:
                self._dropState(state, cancelRequest=True)
                state.url = newUrl
                self._submitParse(state)
                self._payloadOverrides.pop(oldUrl, None)
                break
        self.linesReordered.emit()

    def _buildPayload(self, url: str) -> dict[str, Any]:
        payload = self._payload.copy()
        payload.update(self._payloadOverrides.get(url, {}))
        payload["url"] = url
        cid = payload.get("category")
        if cid:
            folder = categoryService.folderOf(cid)
            if folder:
                payload["path"] = Path(folder)
        return payload

    def _submitParse(self, state: _LineParseState) -> None:
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
            self.parseFailed.emit(state.url, str(error))
            return

        state.callbackId = callbackId
        self._activeParses[callbackId] = state
        self.parsingBusyChanged.emit(True)

    def _dropState(self, state: _LineParseState, cancelRequest: bool, silent: bool = False) -> None:
        # silent: clear/accept 走批量 cleared 信号, 每条不再单独发 lineRemoved
        if cancelRequest and state.callbackId:
            self._activeParses.pop(state.callbackId, None)
            coreService.cancelCallback(state.callbackId)
            self.parsingBusyChanged.emit(bool(self._activeParses))

        hadTask = state.task is not None
        state.callbackId = ""
        state.task = None
        if hadTask and not silent:
            self.lineRemoved.emit(state.url)

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
                state.task = None
                self.parseFailed.emit(state.url, error or self.tr("解析失败"))
                if error:
                    logger.warning("解析任务失败 {}: {}", state.url, error)
                return

            resultTask.applySettings(self._buildPayload(state.url))
            state.task = resultTask
            self.parseSucceeded.emit(state.url, resultTask)
            self.linesReordered.emit()
            return

        # 用户点 OK 时 parse 还没回, callbackId 已搬到 _acceptedPayloads; 这时才到
        acceptedPayload = self._acceptedPayloads.pop(callbackId, None)
        if acceptedPayload is None:
            return

        if error or resultTask is None:
            if error:
                logger.warning("后台确认任务解析失败: {}", error)
            return

        resultTask.applySettings(acceptedPayload)
        self.taskConfirmed.emit(resultTask)
