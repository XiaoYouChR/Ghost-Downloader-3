# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportAny=false, reportImplicitOverride=false, reportInconsistentConstructor=false, reportArgumentType=false, reportAttributeAccessIssue=false, reportUninitializedInstanceVariable=false, reportUnannotatedClassAttribute=false, reportExplicitAny=false

from __future__ import annotations

import asyncio
import os
from asyncio import CancelledError
from asyncio import TaskGroup
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from struct import pack
from struct import unpack
from time import time_ns
from typing import Any
from uuid import uuid4

import niquests
from loguru import logger

from app.bases.models import SpecialFileSize
from app.bases.models import TaskStatus as LegacyTaskStatus
from app.feature_pack.api import FormField
from app.feature_pack.api import SingleFileTask
from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskForm
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage
from app.supports.config import DEFAULT_HEADERS
from app.supports.config import cfg
from app.supports.sysio import ftruncate
from app.supports.sysio import pwrite
from app.supports.utils import getProxies
from app.supports.utils import sanitizeFilename
from app.supports.utils import splitRequestHeadersAndCookies

_HTTP_TASK_PACK_ID = "http_pack"
_HTTP_TASK_KIND = "http_download"
_HTTP_STAGE_KIND = "http_download"
_HTTP_TASK_VERSION = 1
_HTTP_STAGE_VERSION = 1
_DEFAULT_STAGE_NAME = "HTTP 下载"


def _copyHeaders(headers: Mapping[str, str] | None, *, useDefaults: bool = False) -> dict[str, str]:
    if headers:
        return {str(key): str(value) for key, value in headers.items()}
    if useDefaults:
        return DEFAULT_HEADERS.copy()
    return {}


def _copyProxies(proxies: Mapping[str, str] | None) -> dict[str, str] | None:
    if proxies is None:
        return None
    return {str(key): str(value) for key, value in proxies.items()}


def _normalizeChunks(value: int | None) -> int:
    if value is None or isinstance(value, bool):
        return max(1, int(cfg.preBlockNum.value))
    return max(1, int(value))


def _normalizeFileSize(value: int | None) -> int:
    if value is None or isinstance(value, bool):
        return SpecialFileSize.UNKNOWN
    normalized = int(value)
    if normalized < 0:
        return SpecialFileSize.UNKNOWN
    return normalized


def _normalizeState(value: str | LegacyTaskStatus | object) -> str:
    if isinstance(value, LegacyTaskStatus):
        return value.name.lower()
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"completed", "failed", "paused", "running", "waiting"}:
            return normalized
    return "waiting"


def _legacyStatus(value: str) -> LegacyTaskStatus:
    return {
        "waiting": LegacyTaskStatus.WAITING,
        "running": LegacyTaskStatus.RUNNING,
        "paused": LegacyTaskStatus.PAUSED,
        "completed": LegacyTaskStatus.COMPLETED,
        "failed": LegacyTaskStatus.FAILED,
    }[_normalizeState(value)]


class HttpTaskStage(TaskStage):
    recordTaskPackId = _HTTP_TASK_PACK_ID
    recordTaskKind = _HTTP_TASK_KIND
    recordTaskVersion = _HTTP_TASK_VERSION
    recordKind = _HTTP_STAGE_KIND
    recordVersion = _HTTP_STAGE_VERSION

    def __init__(
        self,
        *,
        id: str | None = None,
        stageIndex: int = 1,
        url: str,
        fileSize: int = SpecialFileSize.UNKNOWN,
        headers: Mapping[str, str] | None = None,
        proxies: Mapping[str, str] | None = None,
        resolvePath: str = "",
        blockNum: int = 1,
        supportsRange: bool = True,
        accelerated: bool = False,
        kind: str = _HTTP_STAGE_KIND,
        version: int = _HTTP_STAGE_VERSION,
        name: str = _DEFAULT_STAGE_NAME,
        state: str | LegacyTaskStatus = "waiting",
        progress: float = 0.0,
        doneBytes: int = 0,
        speed: int = 0,
        error: str = "",
    ) -> None:
        super().__init__(
            id=id or f"http-stage-{uuid4().hex}",
            kind=kind,
            version=version,
            name=name,
        )
        self.stageIndex = stageIndex
        self.url = str(url).strip()
        self.fileSize = _normalizeFileSize(fileSize)
        self.headers = _copyHeaders(headers, useDefaults=True)
        self.proxies = _copyProxies(proxies)
        self.resolvePath = str(resolvePath)
        self.blockNum = _normalizeChunks(blockNum)
        self.supportsRange = bool(supportsRange)
        self.accelerated = bool(accelerated)
        self.state = _normalizeState(state)
        self.progress = max(0.0, min(float(progress), 100.0))
        self.doneBytes = max(0, int(doneBytes))
        self.speed = max(0, int(speed))
        self.error = str(error)

    @property
    def receivedBytes(self) -> int:
        return self.doneBytes

    @receivedBytes.setter
    def receivedBytes(self, value: int) -> None:
        self.doneBytes = max(0, int(value))

    @property
    def status(self) -> LegacyTaskStatus:
        return _legacyStatus(self.state)

    @status.setter
    def status(self, value: LegacyTaskStatus | str) -> None:
        self.setStatus(value, emitSignals=False)

    def canPause(self) -> bool:
        return self.supportsRange

    def configure(self, config: TaskConfig) -> None:
        self.url = str(config.source).strip()
        self.headers = _copyHeaders(config.headers, useDefaults=True)
        self.proxies = _copyProxies(config.proxies)
        self.blockNum = _normalizeChunks(config.chunks)

    async def pause(self) -> None:
        self.setStatus("paused")

    async def run(self) -> None:
        await HttpWorker(self).run()

    def reset(self, notifyTask: bool = True) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.speed = 0
        self.error = ""
        task = self._task if isinstance(self._task, HttpTask) else None
        if notifyTask and task is not None:
            task.syncStatusFromStages()
        self.stateChanged.emit(self.state)
        self.progressChanged.emit(self.progress)
        self.snapshotChanged.emit(self.snapshot())

    def setStatus(
        self,
        status: LegacyTaskStatus | str,
        *,
        emitSignals: bool = True,
        notifyTask: bool | None = None,
    ) -> None:
        normalizedStatus = _normalizeState(status)
        progressChanged = False
        stateChanged = self.state != normalizedStatus

        self.state = normalizedStatus
        if normalizedStatus == "completed":
            if self.fileSize > 0:
                self.doneBytes = max(self.doneBytes, self.fileSize)
            if self.progress != 100.0:
                progressChanged = True
            self.progress = 100.0
            self.speed = 0
            self.error = ""
        elif normalizedStatus in {"paused", "waiting"}:
            self.speed = 0
            self.error = ""
        elif normalizedStatus == "failed":
            self.speed = 0

        task = self._task if isinstance(self._task, HttpTask) else None
        if notifyTask is not False and task is not None:
            task.syncStatusFromStages()

        if not emitSignals:
            return

        if stateChanged:
            self.stateChanged.emit(self.state)
        if progressChanged:
            self.progressChanged.emit(self.progress)
        self.snapshotChanged.emit(self.snapshot())

    def setError(self, error: Any, notifyTask: bool = True) -> None:
        message = repr(error).strip() if error is not None else ""
        self.error = message
        self.state = "failed"
        self.speed = 0
        task = self._task if isinstance(self._task, HttpTask) else None
        if notifyTask and task is not None:
            task.syncStatusFromStages()
        self.stateChanged.emit(self.state)
        self.failed.emit(message)
        self.snapshotChanged.emit(self.snapshot())

    def updateTransfer(
        self,
        *,
        doneBytes: int,
        speed: int,
        progress: float,
        notifyTask: bool = True,
    ) -> None:
        self.doneBytes = max(0, int(doneBytes))
        self.speed = max(0, int(speed))
        self.progress = max(0.0, min(float(progress), 100.0))
        task = self._task if isinstance(self._task, HttpTask) else None
        if notifyTask and task is not None:
            task.syncStatusFromStages()
        self.progressChanged.emit(self.progress)
        self.snapshotChanged.emit(self.snapshot())

    def snapshot(self) -> StageSnapshot:
        return StageSnapshot(
            id=self.id,
            kind=self.kind,
            name=self.name,
            state=self.state,
            progress=self.progress,
            doneBytes=self.doneBytes,
            speed=self.speed,
            error=self.error,
        )

    def persistenceState(self) -> dict[str, object]:
        return {
            "stageIndex": self.stageIndex,
            "url": self.url,
            "fileSize": self.fileSize,
            "headers": dict(self.headers),
            "proxies": None if self.proxies is None else dict(self.proxies),
            "resolvePath": self.resolvePath,
            "blockNum": self.blockNum,
            "supportsRange": self.supportsRange,
            "accelerated": self.accelerated,
            "state": self.state,
            "progress": self.progress,
            "doneBytes": self.doneBytes,
            "speed": self.speed,
            "error": self.error,
        }

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        rawStageIndex = state.get("stageIndex")
        rawUrl = state.get("url")
        rawFileSize = state.get("fileSize")
        rawResolvePath = state.get("resolvePath")
        rawBlockNum = state.get("blockNum")
        rawHeaders = state.get("headers")
        rawProxies = state.get("proxies")
        rawSupportsRange = state.get("supportsRange")
        rawAccelerated = state.get("accelerated")
        rawState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawSpeed = state.get("speed")
        rawError = state.get("error")

        if isinstance(rawStageIndex, int) and not isinstance(rawStageIndex, bool):
            self.stageIndex = rawStageIndex
        if isinstance(rawUrl, str):
            self.url = rawUrl
        if isinstance(rawResolvePath, str):
            self.resolvePath = rawResolvePath
        if isinstance(rawFileSize, int) and not isinstance(rawFileSize, bool):
            self.fileSize = _normalizeFileSize(rawFileSize)
        if isinstance(rawBlockNum, int) and not isinstance(rawBlockNum, bool):
            self.blockNum = _normalizeChunks(rawBlockNum)
        if isinstance(rawHeaders, Mapping):
            self.headers = _copyHeaders(rawHeaders, useDefaults=True)
        if rawProxies is None:
            self.proxies = None
        elif isinstance(rawProxies, Mapping):
            self.proxies = _copyProxies(rawProxies)
        if isinstance(rawSupportsRange, bool):
            self.supportsRange = rawSupportsRange
        if isinstance(rawAccelerated, bool):
            self.accelerated = rawAccelerated
        if isinstance(rawState, str):
            self.state = _normalizeState(rawState)
        if isinstance(rawProgress, int | float):
            self.progress = max(0.0, min(float(rawProgress), 100.0))
        if isinstance(rawDoneBytes, int) and not isinstance(rawDoneBytes, bool):
            self.doneBytes = max(0, rawDoneBytes)
        if isinstance(rawSpeed, int) and not isinstance(rawSpeed, bool):
            self.speed = max(0, rawSpeed)
        if isinstance(rawError, str):
            self.error = rawError

    @classmethod
    def createPersistentStage(
        cls,
        *,
        id: str,
        kind: str,
        version: int,
        name: str,
        state: Mapping[str, object],
    ) -> "HttpTaskStage":
        rawUrl = state.get("url")
        rawResolvePath = state.get("resolvePath")
        rawHeaders = state.get("headers")
        rawProxies = state.get("proxies")
        rawFileSize = state.get("fileSize")
        rawBlockNum = state.get("blockNum")
        rawSupportsRange = state.get("supportsRange")
        rawAccelerated = state.get("accelerated")
        rawTaskState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawSpeed = state.get("speed")
        rawError = state.get("error")
        rawStageIndex = state.get("stageIndex")

        return cls(
            id=id,
            kind=kind,
            version=version,
            name=name,
            stageIndex=rawStageIndex if isinstance(rawStageIndex, int) else 1,
            url=rawUrl if isinstance(rawUrl, str) else "",
            fileSize=rawFileSize if isinstance(rawFileSize, int) else SpecialFileSize.UNKNOWN,
            headers=rawHeaders if isinstance(rawHeaders, Mapping) else None,
            proxies=rawProxies if isinstance(rawProxies, Mapping) else None,
            resolvePath=rawResolvePath if isinstance(rawResolvePath, str) else "",
            blockNum=rawBlockNum if isinstance(rawBlockNum, int) else 1,
            supportsRange=bool(rawSupportsRange) if isinstance(rawSupportsRange, bool) else True,
            accelerated=bool(rawAccelerated) if isinstance(rawAccelerated, bool) else False,
            state=rawTaskState if isinstance(rawTaskState, str) else "waiting",
            progress=float(rawProgress) if isinstance(rawProgress, int | float) else 0.0,
            doneBytes=rawDoneBytes if isinstance(rawDoneBytes, int) else 0,
            speed=rawSpeed if isinstance(rawSpeed, int) else 0,
            error=rawError if isinstance(rawError, str) else "",
        )


class HttpTask(SingleFileTask):
    recordPackId = _HTTP_TASK_PACK_ID
    recordKind = _HTTP_TASK_KIND
    recordVersion = _HTTP_TASK_VERSION

    def __init__(
        self,
        *,
        id: str | None = None,
        config: TaskConfig | None = None,
        stages: list[TaskStage] | None = None,
        totalBytes: int | None = None,
        supportsRange: bool = True,
        createdAt: int | None = None,
        title: str | None = None,
        url: str | None = None,
        fileSize: int | None = None,
        path: Path | str | None = None,
        headers: Mapping[str, str] | None = None,
        proxies: Mapping[str, str] | None = None,
        blockNum: int | None = None,
    ) -> None:
        if config is None:
            resolvedUrl = str(url or "").strip()
            if not resolvedUrl:
                raise ValueError("HttpTask requires TaskConfig or url")

            resolvedFolder = (
                Path(path)
                if path is not None
                else Path(cfg.downloadFolder.value)
            )
            resolvedName = sanitizeFilename(str(title or "").strip(), fallback="download")
            config = TaskConfig(
                source=resolvedUrl,
                folder=resolvedFolder,
                name=resolvedName,
                headers=_copyHeaders(headers, useDefaults=True),
                proxies=_copyProxies(proxies) if proxies is not None else getProxies(),
                chunks=_normalizeChunks(blockNum),
            )

        normalizedConfig = self._normalizeConfig(config)
        resolvedTotalBytes = fileSize if fileSize is not None else totalBytes
        resolvedStages = stages or [
            HttpTaskStage(
                url=normalizedConfig.source,
                fileSize=_normalizeFileSize(resolvedTotalBytes),
                headers=normalizedConfig.headers,
                proxies=normalizedConfig.proxies,
                resolvePath="",
                blockNum=normalizedConfig.chunks,
                supportsRange=supportsRange,
            )
        ]

        self.createdAt = int(time_ns()) if createdAt is None else int(createdAt)
        self.url = normalizedConfig.source
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.totalBytes = _normalizeFileSize(resolvedTotalBytes)
        self.supportsRange = bool(supportsRange)
        self.target = ""
        self._refreshDownloadInfoOnNextRun = False

        super().__init__(
            id=id or f"http-task-{uuid4().hex}",
            packId=_HTTP_TASK_PACK_ID,
            kind=_HTTP_TASK_KIND,
            version=_HTTP_TASK_VERSION,
            config=normalizedConfig,
            stages=resolvedStages,
        )
        self.syncOutput()
        for stage in self.stages:
            if isinstance(stage, HttpTaskStage):
                stage.configure(self.config)
                stage.fileSize = self.totalBytes
                stage.supportsRange = self.supportsRange

    @property
    def taskId(self) -> str:
        return self.id

    @property
    def title(self) -> str:
        return self.filename

    @property
    def status(self) -> LegacyTaskStatus:
        return _legacyStatus(self.state)

    @property
    def fileSize(self) -> int:
        return self.totalBytes

    @fileSize.setter
    def fileSize(self, value: int) -> None:
        self.totalBytes = _normalizeFileSize(value)
        for stage in self.stages:
            if isinstance(stage, HttpTaskStage):
                stage.fileSize = self.totalBytes

    @property
    def headers(self) -> dict[str, str]:
        return dict(self.config.headers)

    @property
    def proxies(self) -> dict[str, str] | None:
        return None if self.config.proxies is None else dict(self.config.proxies)

    @property
    def blockNum(self) -> int:
        return self.config.chunks

    @property
    def resolvePath(self) -> str:
        return str(self.path)

    @property
    def lastError(self) -> str:
        for stage in reversed(self.stages):
            if isinstance(stage, HttpTaskStage) and stage.error:
                return stage.error
        return ""

    @staticmethod
    def _normalizeConfig(config: TaskConfig) -> TaskConfig:
        return replace(
            config,
            source=str(config.source).strip(),
            folder=Path(config.folder),
            name=sanitizeFilename(config.name, fallback="download"),
            headers=_copyHeaders(config.headers, useDefaults=True),
            proxies=_copyProxies(config.proxies),
            chunks=_normalizeChunks(config.chunks),
        )

    def setTitle(self, title: str) -> None:
        self.rename(sanitizeFilename(title, fallback=self.filename or "download"))

    def syncStagePaths(self) -> None:
        self.syncOutput()

    def syncOutput(self) -> None:
        self.target = str(self.path)
        for stage in self.stages:
            if not isinstance(stage, HttpTaskStage):
                continue
            stage.resolvePath = self.target
            stage.fileSize = self.totalBytes
            stage.supportsRange = self.supportsRange

    def applyPayloadToTask(self, payload: dict[str, Any]) -> None:
        updates: dict[str, object] = {}

        rawFolder = payload.get("path")
        if isinstance(rawFolder, (str, Path)):
            updates["folder"] = Path(rawFolder)

        rawHeaders = payload.get("headers")
        if isinstance(rawHeaders, Mapping):
            updates["headers"] = _copyHeaders(rawHeaders, useDefaults=True)

        if "proxies" in payload:
            rawProxies = payload.get("proxies")
            if rawProxies is None:
                updates["proxies"] = None
            elif isinstance(rawProxies, Mapping):
                updates["proxies"] = _copyProxies(rawProxies)

        rawChunks = payload.get("preBlockNum")
        if isinstance(rawChunks, int) and not isinstance(rawChunks, bool):
            updates["chunks"] = _normalizeChunks(rawChunks)

        rawSource = payload.get("url")
        if isinstance(rawSource, str) and rawSource.strip():
            updates["source"] = rawSource.strip()

        rawName = payload.get("filename")
        if isinstance(rawName, str) and rawName.strip():
            updates["name"] = sanitizeFilename(rawName, fallback=self.filename or "download")

        if not updates:
            return

        self.configure(replace(self.config, **updates))

    def setState(self, state: str) -> None:
        normalizedState = _normalizeState(state)
        self.state = normalizedState
        self.stateChanged.emit(normalizedState)
        self.snapshotChanged.emit(self.snapshot())

    def syncStatusFromStages(self) -> LegacyTaskStatus:
        if not self.stages:
            return self.status

        stageStates = [
            stage.state
            for stage in self.stages
            if isinstance(stage, HttpTaskStage)
        ]
        if not stageStates:
            return self.status

        if any(state == "failed" for state in stageStates):
            self.state = "failed"
        elif all(state == "completed" for state in stageStates):
            self.state = "completed"
        elif any(state == "running" for state in stageStates):
            self.state = "running"
        elif all(state == "paused" for state in stageStates):
            self.state = "paused"
        else:
            self.state = "waiting"

        self.progress = sum(stage.progress for stage in self.stages) / len(self.stages)
        self.doneBytes = sum(
            stage.doneBytes
            for stage in self.stages
            if isinstance(stage, HttpTaskStage)
        )
        return self.status

    def setStatus(self, status: LegacyTaskStatus | str) -> LegacyTaskStatus:
        if not self.stages:
            self.state = _normalizeState(status)
            return self.status

        for stage in self.stages:
            if not isinstance(stage, HttpTaskStage):
                continue
            if stage.status == LegacyTaskStatus.COMPLETED:
                continue
            if (
                _legacyStatus(_normalizeState(status)) == LegacyTaskStatus.RUNNING
                and stage.status == LegacyTaskStatus.FAILED
            ):
                stage.reset(notifyTask=False)
            stage.setStatus(status, emitSignals=False, notifyTask=False)

        return self.syncStatusFromStages()

    def configure(self, config: TaskConfig) -> None:
        normalizedConfig = self._normalizeConfig(config)
        shouldRefreshDownloadInfo = (
            normalizedConfig.source != self.config.source
            or normalizedConfig.headers != self.config.headers
            or normalizedConfig.proxies != self.config.proxies
        )
        self.url = normalizedConfig.source
        self._refreshDownloadInfoOnNextRun = (
            self._refreshDownloadInfoOnNextRun or shouldRefreshDownloadInfo
        )
        super().configure(normalizedConfig)

    def editForm(self, _mode: str) -> TaskForm | None:
        return TaskForm(
            title="编辑 HTTP 下载任务",
            fields=(
                FormField(
                    key="source",
                    label="下载链接",
                    kind="text",
                    placeholder="输入 HTTP 或 HTTPS 下载链接",
                ),
                FormField(
                    key="name",
                    label="文件名",
                    kind="text",
                    placeholder="输入输出文件名",
                ),
                FormField(
                    key="folder",
                    label="下载目录",
                    kind="folder",
                    placeholder="选择输出目录",
                ),
                FormField(
                    key="headers",
                    label="请求头",
                    kind="headers",
                    note="使用 key: value 的格式，每行一项",
                ),
                FormField(
                    key="proxies",
                    label="代理",
                    kind="proxy",
                    note="使用 key: value 的格式，每行一项；留空表示不使用代理",
                ),
                FormField(
                    key="chunks",
                    label="分块数",
                    kind="int",
                    min=1,
                    max=256,
                ),
            ),
        )

    async def _refreshDownloadInfo(self) -> None:
        currentStage = next(
            (stage for stage in self.stages if isinstance(stage, HttpTaskStage)),
            None,
        )
        if currentStage is None:
            return

        from .pack import _probeDownloadInfo

        fileSize, supportsRange, _, _ = await _probeDownloadInfo(
            currentStage.url,
            currentStage.headers,
            currentStage.proxies,
        )
        self.fileSize = fileSize
        self.supportsRange = supportsRange
        currentStage.fileSize = fileSize
        currentStage.supportsRange = supportsRange
        self.syncOutput()
        self._refreshDownloadInfoOnNextRun = False

    async def run(self) -> None:
        if self._refreshDownloadInfoOnNextRun:
            currentStage = next(
                (stage for stage in self.stages if isinstance(stage, HttpTaskStage)),
                None,
            )
            try:
                await self._refreshDownloadInfo()
            except Exception as error:
                if currentStage is not None and not currentStage.error:
                    currentStage.setError(error)
                raise

        await super().run()

    def reset(self) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.currentStageIndex = 0
        self._refreshDownloadInfoOnNextRun = True
        for stage in self.stages:
            if isinstance(stage, HttpTaskStage):
                stage.reset(notifyTask=False)
            else:
                stage.reset()
        self.syncStatusFromStages()

    def snapshot(self) -> TaskSnapshot:
        return TaskSnapshot(
            id=self.id,
            packId=self.packId,
            kind=self.kind,
            name=self.filename,
            state=self.state,
            progress=self.progress,
            doneBytes=self.doneBytes,
            totalBytes=max(0, self.totalBytes),
            canPause=self.canPause(),
            target=self.target,
            stages=tuple(stage.snapshot() for stage in self.stages),
        )

    def persistenceState(self) -> dict[str, object]:
        state = super().persistenceState()
        state.update(
            {
                "createdAt": self.createdAt,
                "url": self.url,
                "state": self.state,
                "progress": self.progress,
                "doneBytes": self.doneBytes,
                "totalBytes": self.totalBytes,
                "supportsRange": self.supportsRange,
                "refreshDownloadInfoOnNextRun": self._refreshDownloadInfoOnNextRun,
            }
        )
        return state

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        super().restorePersistentState(state)
        rawCreatedAt = state.get("createdAt")
        rawUrl = state.get("url")
        rawState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawTotalBytes = state.get("totalBytes")
        rawSupportsRange = state.get("supportsRange")
        rawRefresh = state.get("refreshDownloadInfoOnNextRun")

        if isinstance(rawCreatedAt, int) and not isinstance(rawCreatedAt, bool):
            self.createdAt = rawCreatedAt
        if isinstance(rawUrl, str) and rawUrl:
            self.url = rawUrl
        if isinstance(rawState, str):
            self.state = _normalizeState(rawState)
        if isinstance(rawProgress, int | float):
            self.progress = max(0.0, min(float(rawProgress), 100.0))
        if isinstance(rawDoneBytes, int) and not isinstance(rawDoneBytes, bool):
            self.doneBytes = max(0, rawDoneBytes)
        if isinstance(rawTotalBytes, int) and not isinstance(rawTotalBytes, bool):
            self.totalBytes = _normalizeFileSize(rawTotalBytes)
        if isinstance(rawSupportsRange, bool):
            self.supportsRange = rawSupportsRange
        if isinstance(rawRefresh, bool):
            self._refreshDownloadInfoOnNextRun = rawRefresh
        self.syncOutput()

    @classmethod
    def createPersistentTask(
        cls,
        *,
        id: str,
        packId: str,
        kind: str,
        version: int,
        config: TaskConfig,
        stages: list[TaskStage],
        state: Mapping[str, object],
    ) -> "HttpTask":
        _ = packId
        _ = kind
        _ = version
        rawTotalBytes = state.get("totalBytes")
        rawSupportsRange = state.get("supportsRange")
        rawCreatedAt = state.get("createdAt")

        return cls(
            id=id,
            config=config,
            stages=stages,
            totalBytes=rawTotalBytes if isinstance(rawTotalBytes, int) else SpecialFileSize.UNKNOWN,
            supportsRange=bool(rawSupportsRange) if isinstance(rawSupportsRange, bool) else True,
            createdAt=rawCreatedAt if isinstance(rawCreatedAt, int) else None,
        )

    def __hash__(self) -> int:
        return hash(self.id)

    def occupiesDownloadSlot(self) -> bool:
        return self.state == "running"

    def willOccupyDownloadSlotWhenStarted(self) -> bool:
        return True


@dataclass(slots=True)
class HttpSubworker:
    start: int
    progress: int
    end: int


class HttpWorker:
    def __init__(self, stage: HttpTaskStage) -> None:
        self.stage = stage
        self.speedHistory: list[int] = []
        self.accelCheckTime = 0.0
        self.requestHeaders, self.requestCookies = splitRequestHeadersAndCookies(stage.headers)

    @property
    def _task(self) -> HttpTask | None:
        task = getattr(self.stage, "_task", None)
        return task if isinstance(task, HttpTask) else None

    def reassignSubworker(self) -> None:
        if self.stage.fileSize <= 0:
            return

        slowestSubworker = max(
            self.subworkers,
            key=lambda subworker: subworker.end - subworker.progress,
        )
        remainingBytes = slowestSubworker.end - slowestSubworker.progress
        if remainingBytes < cfg.maxReassignSize.value * 1048576:
            return

        base = remainingBytes // 2
        remainder = remainingBytes % 2
        slowestSubworker.end = slowestSubworker.progress + base + remainder
        newSubworker = HttpSubworker(
            slowestSubworker.end + 1,
            slowestSubworker.end + 1,
            slowestSubworker.end + base,
        )
        self.subworkers.insert(self.subworkers.index(slowestSubworker) + 1, newSubworker)
        self.taskGroup.create_task(self.handleSubworker(newSubworker))

    def _buildRangeHeaders(self, rangeValue: str) -> dict[str, str]:
        requestHeaders = self.requestHeaders.copy()
        requestHeaders["range"] = rangeValue
        requestHeaders["accept-encoding"] = "identity"
        return requestHeaders

    async def handleSubworker(self, subworker: HttpSubworker) -> None:
        if subworker.end == SpecialFileSize.UNKNOWN:
            while True:
                try:
                    response = await self.client.get(
                        self.stage.url,
                        headers=self._buildRangeHeaders(f"bytes={subworker.progress}-"),
                        cookies=self.requestCookies,
                        proxies=self.stage.proxies,
                        verify=cfg.SSLVerify.value,
                        allow_redirects=True,
                        stream=True,
                    )
                    try:
                        response.raise_for_status()
                        if response.status_code != 206:
                            raise RuntimeError(f"服务器拒绝了范围请求，状态码：{response.status_code}")

                        async for chunk in await response.iter_raw(chunk_size=65536):
                            if not chunk:
                                continue

                            await cfg.checkSpeedLimitation()
                            pwrite(self.fileHandle, chunk, subworker.progress)
                            subworker.progress += len(chunk)
                            cfg.globalSpeed += len(chunk)
                    finally:
                        await response.close()

                    return
                except Exception as error:
                    logger.opt(exception=error).error(
                        "{} 的未知大小分片 {} 连接中断，5 秒后重试",
                        self.stage.resolvePath,
                        subworker,
                    )
                    await asyncio.sleep(5)

        if subworker.end == SpecialFileSize.NOT_SUPPORTED:
            while True:
                try:
                    ftruncate(self.fileHandle, 0)
                    subworker.progress = 0

                    response = await self.client.get(
                        self.stage.url,
                        headers=self.requestHeaders,
                        cookies=self.requestCookies,
                        proxies=self.stage.proxies,
                        verify=cfg.SSLVerify.value,
                        allow_redirects=True,
                        stream=True,
                    )
                    try:
                        response.raise_for_status()
                        if response.status_code not in {200, 206}:
                            raise RuntimeError(f"服务器返回了异常状态码：{response.status_code}")

                        async for chunk in await response.iter_raw(chunk_size=65536):
                            if not chunk:
                                continue

                            await cfg.checkSpeedLimitation()
                            pwrite(self.fileHandle, chunk, subworker.progress)
                            subworker.progress += len(chunk)
                            cfg.globalSpeed += len(chunk)
                    finally:
                        await response.close()

                    ftruncate(self.fileHandle, subworker.progress)
                    return
                except Exception as error:
                    logger.opt(exception=error).error(
                        "{} 不支持断点续传，已从头开始重试",
                        self.stage.resolvePath,
                    )
                    await asyncio.sleep(5)

        while subworker.progress < subworker.end:
            try:
                response = await self.client.get(
                    self.stage.url,
                    headers=self._buildRangeHeaders(f"bytes={subworker.progress}-{subworker.end}"),
                    cookies=self.requestCookies,
                    proxies=self.stage.proxies,
                    verify=cfg.SSLVerify.value,
                    allow_redirects=True,
                    stream=True,
                )
                try:
                    response.raise_for_status()
                    if response.status_code != 206:
                        raise RuntimeError(f"服务器拒绝了范围请求，状态码：{response.status_code}")

                    async for chunk in await response.iter_raw(chunk_size=65536):
                        if not chunk:
                            continue

                        await cfg.checkSpeedLimitation()
                        offset = subworker.progress
                        pwrite(self.fileHandle, chunk, offset)
                        subworker.progress += len(chunk)
                        cfg.globalSpeed += len(chunk)
                        if subworker.progress >= subworker.end:
                            break
                finally:
                    await response.close()

                if subworker.progress > subworker.end:
                    subworker.progress = subworker.end
            except Exception as error:
                logger.opt(exception=error).error(
                    "{} 的分片 {} 连接中断，5 秒后重试",
                    self.stage.resolvePath,
                    subworker,
                )
                await asyncio.sleep(5)

        self.reassignSubworker()

    def checkIfAutoAcceleration(self) -> None:
        if self.stage.accelerated or not cfg.autoSpeedUp.value:
            return

        self.speedHistory.append(self.stage.speed)
        if len(self.speedHistory) > 5:
            self.speedHistory.pop(0)
        if len(self.speedHistory) < 5:
            return

        avgSpeed = sum(self.speedHistory) / len(self.speedHistory)
        if avgSpeed == 0:
            return

        maxDeviation = max(
            abs(speed - avgSpeed) / avgSpeed
            for speed in self.speedHistory
        )
        if maxDeviation > 0.15:
            return

        if self.accelCheckTime == 0:
            self.accelInitialWorkers = len(self.subworkers)
            self.accelInitialSpeed = avgSpeed
            self.accelCheckTime = asyncio.get_event_loop().time()

            for _ in range(4):
                self.reassignSubworker()
        else:
            elapsedTime = asyncio.get_event_loop().time() - self.accelCheckTime
            if elapsedTime <= 5:
                return

            currentWorkers = len(self.subworkers)
            workerIncreaseRatio = (
                (currentWorkers - self.accelInitialWorkers) / self.accelInitialWorkers
            )
            speedIncreaseRatio = (
                (avgSpeed - self.accelInitialSpeed) / self.accelInitialSpeed
            )

            if speedIncreaseRatio < 0.8 * workerIncreaseRatio:
                self.stage.accelerated = True
                logger.info(
                    "自动加速已禁用，subworker 增加比: {:.2%}, 速度提升比: {:.2%}",
                    workerIncreaseRatio,
                    speedIncreaseRatio,
                )
            else:
                self.accelCheckTime = 0
                logger.info(
                    "继续自动加速，subworker 增加比: {:.2%}, 速度提升比: {:.2%}",
                    workerIncreaseRatio,
                    speedIncreaseRatio,
                )

    async def supervisor(self) -> None:
        recordFileHandle = None
        if self.stage.supportsRange:
            recordFileHandle = open(Path(self.stage.resolvePath + ".ghd"), "wb")
        try:
            self.stage.receivedBytes = sum(
                subworker.progress - subworker.start
                for subworker in self.subworkers
            )
            while True:
                if recordFileHandle is not None:
                    data = tuple(
                        value
                        for subworker in self.subworkers
                        for value in (
                            subworker.start,
                            subworker.progress,
                            subworker.end,
                        )
                    )
                    recordFileHandle.seek(0)
                    recordFileHandle.write(pack("<" + "Q" * len(data), *data))
                    recordFileHandle.flush()
                    recordFileHandle.truncate()

                doneBytes = sum(
                    subworker.progress - subworker.start
                    for subworker in self.subworkers
                )
                speed = doneBytes - self.stage.receivedBytes
                if self.stage.fileSize > 0:
                    progress = (doneBytes / self.stage.fileSize) * 100
                else:
                    progress = 0.0
                self.stage.updateTransfer(
                    doneBytes=doneBytes,
                    speed=speed,
                    progress=progress,
                )

                task = self._task
                if task is not None:
                    task.doneBytes = doneBytes
                    task.totalBytes = self.stage.fileSize

                self.checkIfAutoAcceleration()
                await asyncio.sleep(1)
        except CancelledError:
            logger.info("{} 停止下载", self.stage.resolvePath)
        except Exception as error:
            logger.opt(exception=error).error("{} 的监控协程异常退出", self.stage.resolvePath)
        finally:
            if recordFileHandle is not None:
                recordFileHandle.close()

    def restoreProgress(self) -> bool:
        recordFile = Path(self.stage.resolvePath + ".ghd")
        if recordFile.exists():
            try:
                with open(recordFile, "rb") as file:
                    while True:
                        data = file.read(24)
                        if not data:
                            break

                        start, progress, end = unpack("<QQQ", data)
                        self.subworkers.append(HttpSubworker(start, progress, end))
                return True
            except Exception as error:
                logger.opt(exception=error).error("恢复下载分片失败 {}", self.stage.resolvePath)
                self.subworkers.clear()
                return False

        return False

    def generateSubworkers(self) -> None:
        if not self.stage.supportsRange:
            self.subworkers.append(HttpSubworker(0, 0, SpecialFileSize.NOT_SUPPORTED))
            return

        if self.stage.fileSize == SpecialFileSize.UNKNOWN:
            self.subworkers.append(HttpSubworker(0, 0, SpecialFileSize.UNKNOWN))
            return

        step = self.stage.fileSize // self.stage.blockNum
        start = 0
        for _ in range(self.stage.blockNum - 1):
            end = start + step - 1
            self.subworkers.append(HttpSubworker(start, start, end))
            start = end + 1

        self.subworkers.append(HttpSubworker(start, start, self.stage.fileSize - 1))

    def _cleanupRecordFile(self) -> None:
        target = Path(self.stage.resolvePath + ".ghd")
        try:
            if target.is_file() or target.is_symlink():
                target.unlink()
        except Exception as error:
            logger.opt(exception=error).error("failed to cleanup temporary file {}", target)

    async def run(self) -> None:
        self.taskGroup = TaskGroup()
        self.subworkers: list[HttpSubworker] = []
        self.client = niquests.AsyncSession(happy_eyeballs=True, pool_maxsize=256)
        self.client.trust_env = False
        shouldCleanupRecordFile = False
        Path(self.stage.resolvePath).parent.mkdir(parents=True, exist_ok=True)
        self.stage.setStatus("running")

        restored = False
        if self.stage.supportsRange:
            restored = self.restoreProgress()
        else:
            self._cleanupRecordFile()

        if not restored:
            logger.info("正在为 {} 生成下载分片", self.stage.resolvePath)
            self.generateSubworkers()
        else:
            logger.info("从进度文件恢复下载分片 {}", self.stage.resolvePath)

        openMode = os.O_RDWR | os.O_CREAT
        if not self.stage.supportsRange:
            openMode |= os.O_TRUNC
        self.fileHandle = os.open(self.stage.resolvePath, openMode, 0o666)

        if not restored and self.stage.fileSize > 0:
            try:
                ftruncate(self.fileHandle, self.stage.fileSize)
            except Exception as error:
                logger.opt(exception=error).error("{} 预分配文件大小失败", self.stage.resolvePath)

        supervisor = asyncio.create_task(self.supervisor())

        try:
            async with self.taskGroup:
                for subworker in self.subworkers:
                    self.taskGroup.create_task(self.handleSubworker(subworker))

            self.stage.setStatus("completed")
            shouldCleanupRecordFile = True
            logger.info("{} 下载完成", self.stage.resolvePath)
        except CancelledError:
            self.stage.setStatus("paused")
            raise
        except Exception as error:
            self.stage.setError(error)
            logger.opt(exception=error).error("{} 下载阶段失败", self.stage.resolvePath)
            raise
        finally:
            if not supervisor.done():
                supervisor.cancel()
                with suppress(asyncio.CancelledError):
                    await supervisor
            os.close(self.fileHandle)
            await self.client.close()
            if shouldCleanupRecordFile:
                self._cleanupRecordFile()


__all__ = ["HttpSubworker", "HttpTask", "HttpTaskStage", "HttpWorker"]
