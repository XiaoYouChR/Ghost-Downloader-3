from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal
from loguru import logger

if TYPE_CHECKING:
    from app.models.pack import BinaryRuntime


@dataclass(frozen=True)
class RuntimeStatus:
    runtimeId: str
    name: str
    path: str = ""
    version: str = ""
    error: str = ""
    isBusy: bool = False


class RuntimeStatusService(QObject):
    statusChanged = Signal(object)

    def __init__(self, coroutineRunner, parent=None):
        super().__init__(parent)
        self._coroutineRunner = coroutineRunner
        self._statuses: dict[str, RuntimeStatus] = {}
        self._workIds: dict[str, str] = {}

    def status(self, runtime: BinaryRuntime) -> RuntimeStatus:
        status = self._statuses.get(runtime.runtimeId)
        if status is not None:
            return status
        return RuntimeStatus(runtime.runtimeId, runtime.name, path=runtime.path())

    def refreshStatus(self, runtime: BinaryRuntime) -> None:
        runtimeId = runtime.runtimeId
        current = self._statuses.get(runtimeId)
        if current is not None and not current.isBusy:
            path = runtime.path()
            if current.path == path:
                return
        self._probe(runtime)

    def invalidate(self, runtime: BinaryRuntime) -> None:
        runtimeId = runtime.runtimeId
        workId = self._workIds.get(runtimeId)
        if workId:
            self._coroutineRunner.cancel(workId)
            self._workIds.pop(runtimeId, None)
        self._probe(runtime)

    def _probe(self, runtime: BinaryRuntime) -> None:
        runtimeId = runtime.runtimeId
        path = runtime.path()
        name = runtime.name

        status = RuntimeStatus(runtimeId, name, path=path, isBusy=True)
        self._statuses[runtimeId] = status
        self.statusChanged.emit(status)

        try:
            self._workIds[runtimeId] = self._coroutineRunner.submit(
                runtime.probeVersion(),
                done=self._onProbeFinished,
                failed=self._onProbeFailed,
                runtimeId=runtimeId,
                name=name,
                path=path,
            )
        except Exception as e:
            logger.opt(exception=e).error("runtime probe submit failed: {}", runtimeId)
            self._onProbeFailed(repr(e), runtimeId, name, path)

    def _onProbeFinished(self, version: str, runtimeId: str, name: str, path: str) -> None:
        self._workIds.pop(runtimeId, None)
        status = RuntimeStatus(runtimeId, name, path=path, version=version)
        self._statuses[runtimeId] = status
        self.statusChanged.emit(status)

    def _onProbeFailed(self, error: str, runtimeId: str, name: str, path: str) -> None:
        self._workIds.pop(runtimeId, None)
        status = RuntimeStatus(runtimeId, name, path=path, error=error)
        self._statuses[runtimeId] = status
        self.statusChanged.emit(status)

