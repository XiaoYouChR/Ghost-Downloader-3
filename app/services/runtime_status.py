from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from app.models.task import TaskError, toTaskError

if TYPE_CHECKING:
    from app.models.pack import BinaryRuntime


@dataclass(frozen=True)
class RuntimeStatus:
    runtimeId: str
    name: str
    path: str = ""
    version: str = ""
    detail: str = ""
    latestVersion: str = ""
    error: TaskError | None = None
    isBusy: bool = False
    isInstalling: bool = False
    progress: float = 0


class RuntimeStatusService(QObject):
    statusChanged = Signal(object)

    def __init__(self, coroutineRunner, parent=None):
        super().__init__(parent)
        self._coroutineRunner = coroutineRunner
        self._statuses: dict[str, RuntimeStatus] = {}
        self._workIds: dict[str, str] = {}
        self._runtimes: dict[str, BinaryRuntime] = {}
        self._installingIds: set[str] = set()

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
        self._runtimes.pop(runtimeId, None)
        self._probe(runtime)

    def install(self, runtime: BinaryRuntime) -> None:
        runtimeId = runtime.runtimeId
        if runtimeId in self._installingIds:
            return
        workId = self._workIds.pop(runtimeId, None)
        if workId:
            self._coroutineRunner.cancel(workId)

        current = self._statuses.get(runtimeId)
        latestVersion = current.latestVersion if current else ""

        self._installingIds.add(runtimeId)
        self._runtimes[runtimeId] = runtime

        status = RuntimeStatus(runtimeId, runtime.name, isInstalling=True)
        self._statuses[runtimeId] = status
        self.statusChanged.emit(status)

        self._workIds[runtimeId] = self._coroutineRunner.submit(
            self._runInstall(runtime, latestVersion),
            done=self._onInstallFinished,
            failed=self._onInstallFailed,
            runtimeId=runtimeId,
        )

    def cancelInstall(self, runtime: BinaryRuntime) -> None:
        runtimeId = runtime.runtimeId
        if runtimeId not in self._installingIds:
            return
        workId = self._workIds.pop(runtimeId, None)
        if workId:
            self._coroutineRunner.cancel(workId)
        self._installingIds.discard(runtimeId)
        self._runtimes.pop(runtimeId, None)
        status = RuntimeStatus(runtimeId, runtime.name, path=runtime.path())
        self._statuses[runtimeId] = status
        self.statusChanged.emit(status)

    async def _runInstall(self, runtime: BinaryRuntime, version: str = "") -> None:
        from app.models.task import TaskStatus

        task = await runtime.createInstallTask(version)
        task.setStatus(TaskStatus.RUNNING)

        def reportProgress(*_args):
            step = next((s for s in task.steps if s.progress > 0), None)
            if step:
                runtimeId = runtime.runtimeId
                current = self._statuses.get(runtimeId)
                if current and current.isInstalling and current.progress != step.progress:
                    status = replace(current, progress=step.progress)
                    self._statuses[runtimeId] = status
                    self.statusChanged.emit(status)

        await task.run(reportProgress, lambda: asyncio.sleep(0))

    def _onInstallFinished(self, _, runtimeId: str) -> None:
        self._installingIds.discard(runtimeId)
        self._workIds.pop(runtimeId, None)
        runtime = self._runtimes.get(runtimeId)
        if runtime:
            self.invalidate(runtime)

    def _onInstallFailed(self, error: Exception, runtimeId: str) -> None:
        if runtimeId not in self._installingIds:
            return
        self._installingIds.discard(runtimeId)
        self._workIds.pop(runtimeId, None)
        self._runtimes.pop(runtimeId, None)
        current = self._statuses.get(runtimeId)
        if current:
            status = replace(current, isInstalling=False, error=toTaskError(error))
            self._statuses[runtimeId] = status
            self.statusChanged.emit(status)

    def _probe(self, runtime: BinaryRuntime) -> None:
        runtimeId = runtime.runtimeId
        path = runtime.path()
        name = runtime.name
        self._runtimes[runtimeId] = runtime

        status = RuntimeStatus(runtimeId, name, path=path, isBusy=True)
        self._statuses[runtimeId] = status
        self.statusChanged.emit(status)

        self._workIds[runtimeId] = self._coroutineRunner.submit(
            runtime.probeVersion(),
            done=self._onProbeFinished,
            failed=self._onProbeFailed,
            runtimeId=runtimeId,
            name=name,
            path=path,
        )

    def _onProbeFinished(self, versionInfo, runtimeId: str, name: str, path: str) -> None:
        self._workIds.pop(runtimeId, None)
        status = RuntimeStatus(
            runtimeId, name, path=path,
            version=versionInfo.version, detail=versionInfo.detail,
        )
        self._statuses[runtimeId] = status
        self.statusChanged.emit(status)

        runtime = self._runtimes.get(runtimeId)
        if runtime and runtime.isAppManaged():
            self._fetchLatest(runtime)
        else:
            self._runtimes.pop(runtimeId, None)

    def _onProbeFailed(self, error: Exception, runtimeId: str, name: str, path: str) -> None:
        self._workIds.pop(runtimeId, None)
        self._runtimes.pop(runtimeId, None)
        status = RuntimeStatus(runtimeId, name, path=path, error=toTaskError(error))
        self._statuses[runtimeId] = status
        self.statusChanged.emit(status)

    def _fetchLatest(self, runtime: BinaryRuntime) -> None:
        runtimeId = runtime.runtimeId
        self._workIds[runtimeId] = self._coroutineRunner.submit(
            runtime.fetchLatestVersion(),
            done=self._onFetchFinished,
            failed=self._onFetchFailed,
            runtimeId=runtimeId,
        )

    def _onFetchFinished(self, latestVersion: str, runtimeId: str) -> None:
        self._workIds.pop(runtimeId, None)
        self._runtimes.pop(runtimeId, None)
        current = self._statuses.get(runtimeId)
        if current and latestVersion:
            status = replace(current, latestVersion=latestVersion)
            self._statuses[runtimeId] = status
            self.statusChanged.emit(status)

    def _onFetchFailed(self, error: Exception, runtimeId: str) -> None:
        self._workIds.pop(runtimeId, None)
        self._runtimes.pop(runtimeId, None)
