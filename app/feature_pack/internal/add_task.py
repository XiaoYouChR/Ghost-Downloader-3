# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportAny=false, reportImplicitOverride=false

"""Add-task dialog helpers for Feature Pack V1."""

from __future__ import annotations

from collections.abc import Awaitable
from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Protocol
from typing import final

from PySide6.QtCore import QObject
from PySide6.QtCore import Signal
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from loguru import logger

from app.feature_pack.api import FeatureService
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskInput


TaskCreateCallback = Callable[[Task | None, str | None], None]
RunTaskCoroutine = Callable[[Awaitable[Task], TaskCreateCallback], str]
CancelTaskRequest = Callable[[str], bool]


@dataclass(frozen=True, slots=True, kw_only=True)
class AddTaskInputOverride:
    """Per-source override used while building add-task ``TaskInput`` values."""

    folder: Path | None = None
    name: str | None = None
    headers: dict[str, str] | None = None
    proxies: dict[str, str] | None = None
    chunks: int | None = None
    size: int | None = None
    hints: tuple[dict[str, object], ...] = ()


@dataclass(slots=True)
class _LineState:
    source: str
    requestId: str = ""
    task: Task | None = None
    resultCard: object | None = None


class TaskInputRequestRunner(Protocol):
    """Minimal callback runner required by ``AddTaskDialogSession``."""

    def createTask(
        self,
        data: TaskInput,
        callback: TaskCreateCallback,
    ) -> str:
        """Submit one ``FeatureService.createTask()`` request."""
        ...

    def cancel(self, requestId: str) -> bool:
        """Cancel one pending request when still possible."""
        ...


def _copyHeaders(headers: Mapping[str, str] | None) -> dict[str, str]:
    if headers is None:
        return {}
    return {str(key): str(value) for key, value in headers.items()}


def _copyProxies(
    proxies: Mapping[str, str] | None,
) -> dict[str, str] | None:
    if proxies is None:
        return None
    return {str(key): str(value) for key, value in proxies.items()}


def _normalizeChunks(value: int | None) -> int:
    if value is None or isinstance(value, bool):
        return 1
    return max(1, int(value))


def _normalizeSize(value: int | None) -> int:
    if value is None or isinstance(value, bool):
        return 0
    return max(0, int(value))


def _copyHints(
    hints: Iterable[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    return tuple(dict(hint) for hint in hints)


def buildAddTaskConfig(
    *,
    source: str,
    folder: Path,
    headers: Mapping[str, str] | None = None,
    proxies: Mapping[str, str] | None = None,
    chunks: int = 1,
    name: str = "",
    override: AddTaskInputOverride | None = None,
) -> TaskConfig:
    """Build one normalized ``TaskConfig`` for the add-task flow."""

    resolvedFolder = folder if override is None or override.folder is None else override.folder
    resolvedName = name if override is None or override.name is None else override.name
    resolvedHeaders = (
        headers
        if override is None or override.headers is None
        else override.headers
    )
    resolvedProxies = (
        proxies
        if override is None or override.proxies is None
        else override.proxies
    )
    resolvedChunks = chunks if override is None or override.chunks is None else override.chunks

    return TaskConfig(
        source=source,
        folder=Path(resolvedFolder),
        name=resolvedName,
        headers=_copyHeaders(resolvedHeaders),
        proxies=_copyProxies(resolvedProxies),
        chunks=_normalizeChunks(resolvedChunks),
    )


def buildAddTaskInput(
    *,
    source: str,
    folder: Path,
    headers: Mapping[str, str] | None = None,
    proxies: Mapping[str, str] | None = None,
    chunks: int = 1,
    name: str = "",
    size: int = 0,
    hints: Iterable[Mapping[str, object]] = (),
    override: AddTaskInputOverride | None = None,
) -> TaskInput:
    """Build one normalized ``TaskInput`` for the add-task flow."""

    config = buildAddTaskConfig(
        source=source,
        folder=folder,
        headers=headers,
        proxies=proxies,
        chunks=chunks,
        name=name,
        override=override,
    )
    resolvedSize = size if override is None or override.size is None else override.size
    resolvedHints = (
        hints
        if override is None or not override.hints
        else override.hints
    )

    return TaskInput(
        config=config,
        size=_normalizeSize(resolvedSize),
        hints=_copyHints(resolvedHints),
    )


@final
class FeatureServiceTaskRunner(TaskInputRequestRunner):
    """Adapt ``FeatureService.createTask()`` to the legacy callback runner shape."""

    def __init__(
        self,
        *,
        featureService: FeatureService,
        runTaskCoroutine: RunTaskCoroutine,
        cancelTaskRequest: CancelTaskRequest | None = None,
    ) -> None:
        def _defaultCancelTaskRequest(requestId: str) -> bool:
            _ = requestId
            return False

        self._featureService = featureService
        self._runTaskCoroutine = runTaskCoroutine
        self._cancelTaskRequest = (
            cancelTaskRequest
            if cancelTaskRequest is not None
            else _defaultCancelTaskRequest
        )

    def createTask(
        self,
        data: TaskInput,
        callback: TaskCreateCallback,
    ) -> str:
        return self._runTaskCoroutine(self._featureService.createTask(data), callback)

    def cancel(self, requestId: str) -> bool:
        return self._cancelTaskRequest(requestId)


@final
class AddTaskDialogSession(QObject):
    """Track add-task preview lines and route them through Feature Pack V1 services."""

    parsingBusyChanged = Signal(bool)
    parseErrorOccurred = Signal(str, str)
    taskConfirmed = Signal(object)
    resultsChanged = Signal()

    def __init__(
        self,
        *,
        featureService: FeatureService,
        taskRunner: TaskInputRequestRunner,
        resultCardParent: QWidget | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._featureService = featureService
        self._taskRunner = taskRunner
        self._resultCardParent = resultCardParent
        self._baseFolder = Path(".")
        self._baseHeaders: dict[str, str] = {}
        self._baseProxies: dict[str, str] | None = None
        self._baseChunks = 1
        self._lineStates: list[_LineState] = []
        self._activeRequests: dict[str, _LineState] = {}
        self._acceptedInputs: dict[str, TaskInput] = {}
        self._sourceOverrides: dict[str, AddTaskInputOverride] = {}

    def setBaseConfig(
        self,
        *,
        folder: Path,
        headers: Mapping[str, str] | None = None,
        proxies: Mapping[str, str] | None = None,
        chunks: int = 1,
    ) -> None:
        self._baseFolder = Path(folder)
        self._baseHeaders = _copyHeaders(headers)
        self._baseProxies = _copyProxies(proxies)
        self._baseChunks = _normalizeChunks(chunks)
        self._refreshCurrentInputs()

    def setSourceOverride(
        self,
        source: str,
        override: AddTaskInputOverride | None,
    ) -> None:
        if override is None:
            _ = self._sourceOverrides.pop(source, None)
        else:
            self._sourceOverrides[source] = override
        self._refreshCurrentInputs()

    def buildTaskInput(self, source: str) -> TaskInput:
        return buildAddTaskInput(
            source=source,
            folder=self._baseFolder,
            headers=self._baseHeaders,
            proxies=self._baseProxies,
            chunks=self._baseChunks,
            override=self._sourceOverrides.get(source),
        )

    def previewTasks(self) -> list[Task]:
        return [state.task for state in self._lineStates if state.task is not None]

    def resultCards(self) -> list[object]:
        return [state.resultCard for state in self._lineStates if state.resultCard is not None]

    def canAccept(self) -> bool:
        return any(state.requestId or state.task is not None for state in self._lineStates)

    def updateSources(self, currentSources: list[str]) -> None:
        previousStates = self._lineStates
        previousSources = [state.source for state in previousStates]
        nextStates: list[_LineState] = []
        matcher = SequenceMatcher(a=previousSources, b=currentSources, autojunk=False)

        for tag, oldStart, oldEnd, newStart, newEnd in matcher.get_opcodes():
            if tag == "equal":
                nextStates.extend(previousStates[oldStart:oldEnd])
                continue

            for state in previousStates[oldStart:oldEnd]:
                self._clearState(state, cancelRequest=True)

            for source in currentSources[newStart:newEnd]:
                state = _LineState(source=source)
                self._startCreate(state)
                nextStates.append(state)

        self._lineStates = nextStates
        self._dropRemovedOverrides(currentSources)
        self._syncResultCards()
        self.resultsChanged.emit()

    def addParsedTasks(self, tasks: list[Task]) -> list[str]:
        """Attach already-created tasks to the preview flow."""

        if not tasks:
            return []

        stateBySource = {state.source: state for state in self._lineStates}
        newSources: list[str] = []

        for task in tasks:
            source = task.config.source
            state = stateBySource.get(source)
            if state is not None:
                self._clearState(state, cancelRequest=True)
                try:
                    self._setCreatedTask(state, task)
                except Exception as error:
                    logger.opt(exception=error).error("无法创建解析结果卡片 {}", source)
                    self._failState(state, self.tr("解析结果处理失败"))
                continue

            newSources.append(source)
            state = _LineState(source=source)
            try:
                self._setCreatedTask(state, task)
            except Exception as error:
                logger.opt(exception=error).error("无法创建解析结果卡片 {}", source)
                self._failState(state, self.tr("解析结果处理失败"))
            self._lineStates.append(state)
            stateBySource[source] = state

        self._syncResultCards()
        self.resultsChanged.emit()
        return newSources

    def clear(self) -> None:
        for state in self._lineStates:
            self._clearState(state, cancelRequest=True)

        self._acceptedInputs.clear()
        self._lineStates.clear()
        self._sourceOverrides.clear()
        self._clearResultParent()
        self.resultsChanged.emit()
        self.parsingBusyChanged.emit(bool(self._activeRequests))

    def accept(self) -> list[Task]:
        confirmedTasks: list[Task] = []

        for state in self._lineStates:
            if state.task is not None:
                try:
                    self._applyLatestConfig(state)
                    confirmedTasks.append(state.task)
                except Exception as error:
                    logger.opt(exception=error).error("同步已确认任务设置失败 {}", state.source)
                continue

            if not state.requestId:
                continue

            requestId = state.requestId
            _ = self._activeRequests.pop(requestId, None)
            self._acceptedInputs[requestId] = self.buildTaskInput(state.source)

        self.parsingBusyChanged.emit(bool(self._activeRequests))

        for state in self._lineStates:
            self._clearState(
                state,
                cancelRequest=bool(state.requestId and state.requestId not in self._acceptedInputs),
            )

        self._lineStates.clear()
        self._sourceOverrides.clear()
        self._clearResultParent()
        self.resultsChanged.emit()
        return confirmedTasks

    def _refreshCurrentInputs(self) -> None:
        for state in self._lineStates:
            if state.requestId:
                self._restartCreate(state)
                continue
            if state.task is None:
                continue

            try:
                self._applyLatestConfig(state)
            except Exception as error:
                logger.opt(exception=error).error("同步解析结果设置失败 {}", state.source)
                self._failState(state, self.tr("解析结果处理失败"))

    def _restartCreate(self, state: _LineState) -> None:
        self._cancelRequest(state)
        self._startCreate(state)

    def _startCreate(self, state: _LineState) -> None:
        requestId = ""

        def callback(task: Task | None, error: str | None = None) -> None:
            self._onCreateFinished(requestId, task, error)

        try:
            requestId = self._taskRunner.createTask(self.buildTaskInput(state.source), callback)
        except Exception as error:
            logger.opt(exception=error).error("提交创建任务请求失败 {}", state.source)
            self.parseErrorOccurred.emit(state.source, str(error))
            return

        state.requestId = requestId
        self._activeRequests[requestId] = state
        self.parsingBusyChanged.emit(True)

    def _applyLatestConfig(self, state: _LineState) -> None:
        task = state.task
        if task is None:
            return

        config = self.buildTaskInput(state.source).config
        self._featureService.configureTask(task.id, config)

    def _setCreatedTask(self, state: _LineState, task: Task) -> None:
        state.task = task
        self._applyLatestConfig(state)
        state.resultCard = self._featureService.createResultCard(
            task,
            self._resultCardParent,
        )

    def _cancelRequest(self, state: _LineState) -> None:
        requestId = state.requestId
        if not requestId:
            return

        state.requestId = ""
        _ = self._activeRequests.pop(requestId, None)
        _ = self._taskRunner.cancel(requestId)
        self.parsingBusyChanged.emit(bool(self._activeRequests))

    def _clearState(self, state: _LineState, cancelRequest: bool) -> None:
        if cancelRequest:
            self._cancelRequest(state)

        state.requestId = ""
        self._removeResultCard(state)
        state.task = None
        state.resultCard = None

    def _removeResultCard(self, state: _LineState) -> None:
        resultCard = state.resultCard
        if resultCard is None:
            return

        layout = getattr(self._resultCardParent, "scrollLayout", None)
        if layout is not None and hasattr(layout, "removeWidget"):
            _ = layout.removeWidget(resultCard)

        deleteLater = getattr(resultCard, "deleteLater", None)
        if callable(deleteLater):
            _ = deleteLater()

        state.resultCard = None
        updateGeometry = getattr(self._resultCardParent, "updateGeometry", None)
        if callable(updateGeometry):
            _ = updateGeometry()

    def _clearResultParent(self) -> None:
        clearResults = getattr(self._resultCardParent, "clearResults", None)
        if callable(clearResults):
            _ = clearResults()

    def _syncResultCards(self) -> None:
        layout = getattr(self._resultCardParent, "scrollLayout", None)
        if layout is None:
            return

        visibleIndex = 0
        for state in self._lineStates:
            resultCard = state.resultCard
            if resultCard is None:
                continue

            if layout.indexOf(resultCard) != visibleIndex:
                _ = layout.insertWidget(
                    visibleIndex,
                    resultCard,
                    alignment=Qt.AlignmentFlag.AlignTop,
                )
            visibleIndex += 1

        updateGeometry = getattr(self._resultCardParent, "updateGeometry", None)
        if callable(updateGeometry):
            _ = updateGeometry()

    def _failState(self, state: _LineState, errorMessage: str) -> None:
        state.task = None
        state.resultCard = None
        self.parseErrorOccurred.emit(state.source, errorMessage)

    def _dropRemovedOverrides(self, sources: list[str]) -> None:
        activeSources = set(sources)
        self._sourceOverrides = {
            source: override
            for source, override in self._sourceOverrides.items()
            if source in activeSources
        }

    def _onCreateFinished(
        self,
        requestId: str,
        task: Task | None,
        error: str | None = None,
    ) -> None:
        state = self._activeRequests.pop(requestId, None)
        if state is not None:
            self.parsingBusyChanged.emit(bool(self._activeRequests))
            state.requestId = ""

            if error or task is None:
                self._failState(state, error or self.tr("解析失败"))
                if error:
                    logger.warning("创建任务失败 {}: {}", state.source, error)
                self.resultsChanged.emit()
                return

            try:
                self._setCreatedTask(state, task)
            except Exception as callbackError:
                logger.opt(exception=callbackError).error("无法创建解析结果卡片 {}", state.source)
                self._failState(state, self.tr("解析结果处理失败"))
            self._syncResultCards()
            self.resultsChanged.emit()
            return

        acceptedInput = self._acceptedInputs.pop(requestId, None)
        if acceptedInput is None:
            return

        if error or task is None:
            if error:
                logger.warning("后台确认任务创建失败: {}", error)
            return

        try:
            self._featureService.configureTask(task.id, acceptedInput.config)
            self.taskConfirmed.emit(task)
        except Exception as callbackError:
            logger.opt(exception=callbackError).error(
                "无法创建任务卡片 {}",
                getattr(task.snapshot(), "name", "Unknown"),
            )


__all__ = [
    "AddTaskDialogSession",
    "AddTaskInputOverride",
    "FeatureServiceTaskRunner",
    "TaskInputRequestRunner",
    "buildAddTaskConfig",
    "buildAddTaskInput",
]
