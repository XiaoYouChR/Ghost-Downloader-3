# pyright: reportAny=false, reportExplicitAny=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportAttributeAccessIssue=false, reportImplicitOverride=false, reportInconsistentConstructor=false, reportUnannotatedClassAttribute=false, reportArgumentType=false, reportPrivateLocalImportUsage=false, reportPropertyTypeMismatch=false, reportUnusedCallResult=false, reportUninitializedInstanceVariable=false

from __future__ import annotations

import asyncio
import os
import ssl
from asyncio import CancelledError
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from pathlib import PurePosixPath
from struct import pack
from struct import unpack
from time import time_ns
from typing import Any
from typing import cast
from urllib.parse import unquote
from urllib.parse import urlparse
from uuid import uuid4

import aioftp
from loguru import logger

from app.bases.models import SpecialFileSize
from app.bases.models import TaskStatus as LegacyTaskStatus
from app.feature_pack.api import FormField
from app.feature_pack.api import MultiFileTask
from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskFile
from app.feature_pack.api import TaskForm
from app.feature_pack.api import TaskInput
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage
from app.supports.config import cfg
from app.supports.sysio import ftruncate
from app.supports.sysio import pwrite
from app.supports.utils import getProxies
from app.supports.utils import sanitizeFilename


FTP_CONNECTION_TIMEOUT = 15
FTP_SOCKET_TIMEOUT = 30
FTP_PATH_TIMEOUT = 30
FTP_CHUNK_SIZE = 65536
FTP_RETRY_DELAY = 5
FTP_DEFAULT_PORT = 21
FTPS_DEFAULT_PORT = 990

_FTP_TASK_PACK_ID = "ftp_pack"
_FTP_TASK_KIND = "ftp_download"
_FTP_STAGE_KIND = "ftp_download"
_FTP_TASK_VERSION = 1
_FTP_STAGE_VERSION = 1
_DEFAULT_STAGE_NAME = "FTP 下载"


def _copyProxies(
    proxies: Mapping[str, str] | None,
) -> dict[str, str] | None:
    if proxies is None:
        return None
    return {str(key): str(value) for key, value in proxies.items()}


def _normalizeChunks(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return max(1, int(cfg.preBlockNum.value))
    return max(1, int(value))


def _normalizeFileSize(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return SpecialFileSize.UNKNOWN
    return value if value > 0 else SpecialFileSize.UNKNOWN


def _parsePositiveSize(value: object) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        return SpecialFileSize.UNKNOWN
    return size if size > 0 else SpecialFileSize.UNKNOWN


def _normalizeState(value: str | LegacyTaskStatus | object) -> str:
    if isinstance(value, LegacyTaskStatus):
        return value.name.lower()
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"completed", "failed", "paused", "running", "waiting"}:
            return normalized
    return "waiting"


def _legacyStatus(value: str | LegacyTaskStatus | object) -> LegacyTaskStatus:
    return {
        "waiting": LegacyTaskStatus.WAITING,
        "running": LegacyTaskStatus.RUNNING,
        "paused": LegacyTaskStatus.PAUSED,
        "completed": LegacyTaskStatus.COMPLETED,
        "failed": LegacyTaskStatus.FAILED,
    }[_normalizeState(value)]


def _fileIdForIndex(index: int) -> str:
    return f"file-{index}"


def _fileIndexFromId(fileId: str) -> int:
    prefix, _, suffix = fileId.partition("-")
    if prefix == "file" and suffix.isdecimal():
        return int(suffix)
    if fileId.isdecimal():
        return int(fileId)
    return 0


def _normalizeRelativePath(path: object, *, fallback: str = "ftp_file") -> str:
    text = str(path or "").strip().replace("\\", "/")
    if not text:
        return fallback
    normalizedPath = PurePosixPath(text)
    return str(normalizedPath) if str(normalizedPath) != "." else fallback


def _normalizeRemotePath(path: object) -> str:
    text = str(path or "/").strip().replace("\\", "/")
    if not text:
        return "/"
    return str(PurePosixPath(text))


def _pickProxyUrl(proxies: Mapping[str, str] | None) -> str:
    if not isinstance(proxies, Mapping):
        return ""
    for key in ("ftp", "https", "http"):
        value = str(proxies.get(key) or "").strip()
        if value:
            return value
    return ""


def _buildClientKwargs(proxies: Mapping[str, str] | None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "connection_timeout": FTP_CONNECTION_TIMEOUT,
        "socket_timeout": FTP_SOCKET_TIMEOUT,
        "path_timeout": FTP_PATH_TIMEOUT,
    }

    proxyUrl = _pickProxyUrl(proxies)
    if not proxyUrl:
        return kwargs

    parsedProxy = urlparse(proxyUrl)
    if parsedProxy.scheme not in {"socks4", "socks5"}:
        raise ValueError("FTP/FTPS 下载目前仅支持 SOCKS4/SOCKS5 代理或直连")
    if not parsedProxy.hostname or not parsedProxy.port:
        raise ValueError("代理配置无效")

    kwargs.update(
        {
            "socks_host": parsedProxy.hostname,
            "socks_port": parsedProxy.port,
            "socks_version": 4 if parsedProxy.scheme == "socks4" else 5,
        }
    )
    if parsedProxy.username:
        kwargs["username"] = unquote(parsedProxy.username)
    if parsedProxy.password:
        kwargs["password"] = unquote(parsedProxy.password)
    return kwargs


@dataclass(frozen=True, slots=True, kw_only=True)
class FtpConnectionInfo:
    host: str
    scheme: str = "ftp"
    port: int = FTP_DEFAULT_PORT
    username: str = "anonymous"
    password: str = "anon@"
    sourcePath: str = "/"
    portSpecified: bool = False


@dataclass(slots=True, kw_only=True)
class FtpRemoteFile:
    index: int
    remotePath: str
    relativePath: str
    size: int
    selected: bool = True
    downloadedBytes: int = 0
    completed: bool = False

    def __post_init__(self) -> None:
        self.remotePath = _normalizeRemotePath(self.remotePath)
        self.relativePath = _normalizeRelativePath(self.relativePath)

    def toTaskFile(self) -> "FtpTaskFile":
        return FtpTaskFile(
            id=_fileIdForIndex(self.index),
            path=self.relativePath,
            size=self.size,
            selected=self.selected,
            doneBytes=self.downloadedBytes,
            finished=self.completed,
            index=self.index,
            remotePath=self.remotePath,
        )


@dataclass(slots=True, kw_only=True)
class FtpTaskFile(TaskFile):
    index: int = 0
    remotePath: str = ""

    def __post_init__(self) -> None:
        self.path = _normalizeRelativePath(self.path)
        self.remotePath = _normalizeRemotePath(self.remotePath or self.path)
        if not self.id:
            self.id = _fileIdForIndex(self.index)

    @property
    def relativePath(self) -> str:
        return self.path

    @property
    def downloadedBytes(self) -> int:
        return self.doneBytes

    @downloadedBytes.setter
    def downloadedBytes(self, value: int) -> None:
        self.doneBytes = max(0, int(value))

    @property
    def completed(self) -> bool:
        return self.finished

    @completed.setter
    def completed(self, value: bool) -> None:
        self.finished = bool(value)


def _connectionInfoFromSource(source: str) -> FtpConnectionInfo:
    parsedUrl = urlparse(source.strip())
    scheme = parsedUrl.scheme.lower()
    if scheme not in {"ftp", "ftps"}:
        raise ValueError("不是有效的 FTP/FTPS 链接")
    if not parsedUrl.hostname:
        raise ValueError("FTP/FTPS 链接缺少主机名")

    sourcePath = PurePosixPath(unquote(parsedUrl.path or "/"))
    return FtpConnectionInfo(
        scheme=scheme,
        host=parsedUrl.hostname,
        port=parsedUrl.port or FTP_DEFAULT_PORT,
        username=unquote(parsedUrl.username or "anonymous"),
        password=unquote(parsedUrl.password or "anon@"),
        sourcePath=str(sourcePath),
        portSpecified=parsedUrl.port is not None,
    )


def _coerceConnectionInfo(
    connectionInfo: FtpConnectionInfo | Mapping[str, object] | None,
    source: str,
) -> FtpConnectionInfo:
    if isinstance(connectionInfo, FtpConnectionInfo):
        return connectionInfo
    if isinstance(connectionInfo, Mapping):
        host = connectionInfo.get("host")
        if not isinstance(host, str) or not host.strip():
            return _connectionInfoFromSource(source)
        scheme = connectionInfo.get("scheme")
        port = connectionInfo.get("port")
        username = connectionInfo.get("username")
        password = connectionInfo.get("password")
        sourcePath = connectionInfo.get("sourcePath")
        portSpecified = connectionInfo.get("portSpecified")
        return FtpConnectionInfo(
            host=host.strip(),
            scheme=scheme if isinstance(scheme, str) and scheme else "ftp",
            port=port if isinstance(port, int) and not isinstance(port, bool) else FTP_DEFAULT_PORT,
            username=username if isinstance(username, str) and username else "anonymous",
            password=password if isinstance(password, str) and password else "anon@",
            sourcePath=sourcePath if isinstance(sourcePath, str) and sourcePath else "/",
            portSpecified=bool(portSpecified) if isinstance(portSpecified, bool) else False,
        )
    return _connectionInfoFromSource(source)


def _connectionAttempts(connectionInfo: FtpConnectionInfo) -> list[tuple[int, str]]:
    scheme = connectionInfo.scheme.lower()
    if scheme != "ftps":
        return [(connectionInfo.port, "plain")]

    if not connectionInfo.portSpecified:
        return [
            (FTP_DEFAULT_PORT, "explicit"),
            (FTPS_DEFAULT_PORT, "implicit"),
        ]

    if connectionInfo.port == FTPS_DEFAULT_PORT:
        return [(connectionInfo.port, "implicit")]

    return [
        (connectionInfo.port, "explicit"),
        (connectionInfo.port, "implicit"),
    ]


def _connectionInfoRecord(connectionInfo: FtpConnectionInfo) -> dict[str, object]:
    return {
        "host": connectionInfo.host,
        "scheme": connectionInfo.scheme,
        "port": connectionInfo.port,
        "username": connectionInfo.username,
        "password": connectionInfo.password,
        "sourcePath": connectionInfo.sourcePath,
        "portSpecified": connectionInfo.portSpecified,
    }


def _normalizeInputConfig(config: TaskConfig) -> TaskConfig:
    rawName = str(config.name).strip()
    return TaskConfig(
        source=str(config.source).strip(),
        folder=Path(config.folder),
        name=sanitizeFilename(rawName) if rawName else "",
        headers={str(key): str(value) for key, value in config.headers.items()},
        proxies=_copyProxies(config.proxies),
        chunks=_normalizeChunks(config.chunks),
    )


def _normalizeConfig(config: TaskConfig) -> TaskConfig:
    normalizedConfig = _normalizeInputConfig(config)
    return replace(
        normalizedConfig,
        name=sanitizeFilename(normalizedConfig.name, fallback="ftp_download"),
    )


def _coerceFtpFile(rawFile: object, fallbackIndex: int) -> FtpTaskFile:
    if isinstance(rawFile, FtpTaskFile):
        return rawFile
    if isinstance(rawFile, FtpRemoteFile):
        return rawFile.toTaskFile()
    if isinstance(rawFile, TaskFile):
        index = _fileIndexFromId(rawFile.id)
        return FtpTaskFile(
            id=rawFile.id,
            path=rawFile.path,
            size=rawFile.size,
            selected=rawFile.selected,
            note=rawFile.note,
            doneBytes=rawFile.doneBytes,
            finished=rawFile.finished,
            index=index,
            remotePath=rawFile.path,
        )
    if isinstance(rawFile, Mapping):
        rawIndex = rawFile.get("index")
        index = (
            rawIndex
            if isinstance(rawIndex, int) and not isinstance(rawIndex, bool)
            else fallbackIndex
        )
        fileId = rawFile.get("id")
        rawRelativePath = rawFile.get("relativePath", rawFile.get("path", ""))
        rawRemotePath = rawFile.get("remotePath", rawRelativePath)
        rawSize = rawFile.get("size")
        rawDoneBytes = rawFile.get("downloadedBytes", rawFile.get("doneBytes", 0))
        note = rawFile.get("note")
        return FtpTaskFile(
            id=fileId if isinstance(fileId, str) and fileId else _fileIdForIndex(index),
            path=_normalizeRelativePath(rawRelativePath),
            size=_normalizeFileSize(rawSize),
            selected=bool(rawFile.get("selected", True)),
            note=note if isinstance(note, str) else "",
            doneBytes=rawDoneBytes if isinstance(rawDoneBytes, int) and not isinstance(rawDoneBytes, bool) else 0,
            finished=bool(rawFile.get("completed", rawFile.get("finished", False))),
            index=index,
            remotePath=_normalizeRemotePath(rawRemotePath),
        )

    raise TypeError(f"Unsupported FTP task file type: {type(rawFile).__name__}")


def _restoreFtpFiles(
    state: Mapping[str, object],
    stages: list[TaskStage],
) -> list[FtpTaskFile]:
    rawFiles = state.get("files")
    rawMetadata = state.get("fileMetadata")
    metadataById: dict[str, Mapping[str, object]] = {}
    if isinstance(rawMetadata, list):
        for item in rawMetadata:
            if not isinstance(item, Mapping):
                continue
            fileId = item.get("id")
            if isinstance(fileId, str):
                metadataById[fileId] = item

    stageByFileId = {
        stage.fileId: stage
        for stage in stages
        if isinstance(stage, FtpTaskStage)
    }
    restoredFiles: list[FtpTaskFile] = []

    if isinstance(rawFiles, list):
        for fallbackIndex, rawFile in enumerate(rawFiles):
            if not isinstance(rawFile, Mapping):
                continue
            fileId = rawFile.get("id")
            if not isinstance(fileId, str) or not fileId:
                continue

            metadata = metadataById.get(fileId, {})
            stage = stageByFileId.get(fileId)
            rawIndex = metadata.get("index")
            rawRemotePath = metadata.get("remotePath")
            rawPath = rawFile.get("path")
            rawSize = rawFile.get("size")
            rawDoneBytes = rawFile.get("doneBytes", 0)
            note = rawFile.get("note")
            restoredFiles.append(
                FtpTaskFile(
                    id=fileId,
                    path=rawPath if isinstance(rawPath, str) else fileId,
                    size=rawSize if isinstance(rawSize, int) and not isinstance(rawSize, bool) else SpecialFileSize.UNKNOWN,
                    selected=bool(rawFile.get("selected", True)),
                    note=note if isinstance(note, str) else "",
                    doneBytes=rawDoneBytes if isinstance(rawDoneBytes, int) and not isinstance(rawDoneBytes, bool) else 0,
                    finished=bool(rawFile.get("finished", False)),
                    index=rawIndex if isinstance(rawIndex, int) and not isinstance(rawIndex, bool) else fallbackIndex,
                    remotePath=(
                        rawRemotePath
                        if isinstance(rawRemotePath, str)
                        else stage.remotePath if stage is not None else str(rawPath or fileId)
                    ),
                )
            )

    if restoredFiles:
        return restoredFiles

    for fallbackIndex, stage in enumerate(stages):
        if not isinstance(stage, FtpTaskStage):
            continue
        restoredFiles.append(
            FtpTaskFile(
                id=stage.fileId,
                path=PurePosixPath(stage.remotePath).name or stage.fileId,
                size=stage.fileSize,
                selected=True,
                doneBytes=stage.doneBytes,
                finished=stage.state == "completed",
                index=stage.fileIndex if stage.fileIndex >= 0 else fallbackIndex,
                remotePath=stage.remotePath,
            )
        )

    return restoredFiles


class FtpTaskStage(TaskStage):
    recordTaskPackId = _FTP_TASK_PACK_ID
    recordTaskKind = _FTP_TASK_KIND
    recordTaskVersion = _FTP_TASK_VERSION
    recordKind = _FTP_STAGE_KIND
    recordVersion = _FTP_STAGE_VERSION

    def __init__(
        self,
        *,
        id: str | None = None,
        stageIndex: int = 1,
        fileIndex: int = 0,
        fileId: str = "",
        remotePath: str,
        fileSize: int = SpecialFileSize.UNKNOWN,
        resolvePath: str = "",
        supportsRange: bool = True,
        accelerated: bool = False,
        blockNum: int = 1,
        proxies: Mapping[str, str] | None = None,
        kind: str = _FTP_STAGE_KIND,
        version: int = _FTP_STAGE_VERSION,
        name: str = _DEFAULT_STAGE_NAME,
        state: str | LegacyTaskStatus = "waiting",
        progress: float = 0.0,
        doneBytes: int = 0,
        speed: int = 0,
        error: str = "",
    ) -> None:
        super().__init__(
            id=id or f"ftp-stage-{uuid4().hex}",
            kind=kind,
            version=version,
            name=name,
        )
        self.stageIndex = max(1, int(stageIndex))
        self.fileIndex = max(0, int(fileIndex))
        self.fileId = fileId or _fileIdForIndex(self.fileIndex)
        self.remotePath = _normalizeRemotePath(remotePath)
        self.fileSize = _normalizeFileSize(fileSize)
        self.resolvePath = str(resolvePath)
        self.supportsRange = bool(supportsRange)
        self.accelerated = bool(accelerated)
        self.blockNum = _normalizeChunks(blockNum)
        self.proxies = _copyProxies(proxies)
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
        self.blockNum = _normalizeChunks(config.chunks)
        self.proxies = _copyProxies(config.proxies)

    async def pause(self) -> None:
        self.setStatus("paused")

    async def run(self) -> None:
        await FtpWorker(self).run()

    def reset(self, notifyTask: bool = True) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.speed = 0
        self.error = ""
        task = self._task if isinstance(self._task, FtpTask) else None
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
        stateChanged = self.state != normalizedStatus
        progressChanged = False

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

        task = self._task if isinstance(self._task, FtpTask) else None
        if notifyTask is not False and task is not None:
            task.syncStatusFromStages()

        if not emitSignals:
            return

        if stateChanged:
            self.stateChanged.emit(self.state)
        if progressChanged:
            self.progressChanged.emit(self.progress)
        self.snapshotChanged.emit(self.snapshot())

    def setError(self, error: object, notifyTask: bool = True) -> None:
        message = repr(error).strip() if error is not None else ""
        self.error = message
        self.state = "failed"
        self.speed = 0
        task = self._task if isinstance(self._task, FtpTask) else None
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
        task = self._task if isinstance(self._task, FtpTask) else None
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
            "fileIndex": self.fileIndex,
            "fileId": self.fileId,
            "remotePath": self.remotePath,
            "fileSize": self.fileSize,
            "resolvePath": self.resolvePath,
            "supportsRange": self.supportsRange,
            "accelerated": self.accelerated,
            "blockNum": self.blockNum,
            "proxies": None if self.proxies is None else dict(self.proxies),
            "state": self.state,
            "progress": self.progress,
            "doneBytes": self.doneBytes,
            "speed": self.speed,
            "error": self.error,
        }

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        rawStageIndex = state.get("stageIndex")
        rawFileIndex = state.get("fileIndex")
        rawFileId = state.get("fileId")
        rawRemotePath = state.get("remotePath")
        rawFileSize = state.get("fileSize")
        rawResolvePath = state.get("resolvePath")
        rawSupportsRange = state.get("supportsRange")
        rawAccelerated = state.get("accelerated")
        rawBlockNum = state.get("blockNum")
        rawProxies = state.get("proxies")
        rawState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawSpeed = state.get("speed")
        rawError = state.get("error")

        if isinstance(rawStageIndex, int) and not isinstance(rawStageIndex, bool):
            self.stageIndex = max(1, rawStageIndex)
        if isinstance(rawFileIndex, int) and not isinstance(rawFileIndex, bool):
            self.fileIndex = max(0, rawFileIndex)
        if isinstance(rawFileId, str) and rawFileId:
            self.fileId = rawFileId
        if isinstance(rawRemotePath, str):
            self.remotePath = _normalizeRemotePath(rawRemotePath)
        if isinstance(rawFileSize, int) and not isinstance(rawFileSize, bool):
            self.fileSize = _normalizeFileSize(rawFileSize)
        if isinstance(rawResolvePath, str):
            self.resolvePath = rawResolvePath
        if isinstance(rawSupportsRange, bool):
            self.supportsRange = rawSupportsRange
        if isinstance(rawAccelerated, bool):
            self.accelerated = rawAccelerated
        if isinstance(rawBlockNum, int) and not isinstance(rawBlockNum, bool):
            self.blockNum = _normalizeChunks(rawBlockNum)
        if rawProxies is None:
            self.proxies = None
        elif isinstance(rawProxies, Mapping):
            self.proxies = _copyProxies(cast(Mapping[str, str], rawProxies))
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
    ) -> "FtpTaskStage":
        rawStageIndex = state.get("stageIndex")
        rawFileIndex = state.get("fileIndex")
        rawFileId = state.get("fileId")
        rawRemotePath = state.get("remotePath")
        rawFileSize = state.get("fileSize")
        rawResolvePath = state.get("resolvePath")
        rawSupportsRange = state.get("supportsRange")
        rawAccelerated = state.get("accelerated")
        rawBlockNum = state.get("blockNum")
        rawProxies = state.get("proxies")
        rawTaskState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawSpeed = state.get("speed")
        rawError = state.get("error")

        return cls(
            id=id,
            kind=kind,
            version=version,
            name=name,
            stageIndex=rawStageIndex if isinstance(rawStageIndex, int) else 1,
            fileIndex=rawFileIndex if isinstance(rawFileIndex, int) else 0,
            fileId=rawFileId if isinstance(rawFileId, str) else "",
            remotePath=rawRemotePath if isinstance(rawRemotePath, str) else "/",
            fileSize=rawFileSize if isinstance(rawFileSize, int) else SpecialFileSize.UNKNOWN,
            resolvePath=rawResolvePath if isinstance(rawResolvePath, str) else "",
            supportsRange=bool(rawSupportsRange) if isinstance(rawSupportsRange, bool) else True,
            accelerated=bool(rawAccelerated) if isinstance(rawAccelerated, bool) else False,
            blockNum=rawBlockNum if isinstance(rawBlockNum, int) else 1,
            proxies=cast(Mapping[str, str], rawProxies) if isinstance(rawProxies, Mapping) else None,
            state=rawTaskState if isinstance(rawTaskState, str) else "waiting",
            progress=float(rawProgress) if isinstance(rawProgress, int | float) else 0.0,
            doneBytes=rawDoneBytes if isinstance(rawDoneBytes, int) else 0,
            speed=rawSpeed if isinstance(rawSpeed, int) else 0,
            error=rawError if isinstance(rawError, str) else "",
        )


class FtpTask(MultiFileTask):
    recordPackId = _FTP_TASK_PACK_ID
    recordKind = _FTP_TASK_KIND
    recordVersion = _FTP_TASK_VERSION

    def __init__(
        self,
        *,
        id: str | None = None,
        config: TaskConfig | None = None,
        stages: list[TaskStage] | None = None,
        files: list[TaskFile | FtpRemoteFile | Mapping[str, object]] | None = None,
        connectionInfo: FtpConnectionInfo | Mapping[str, object] | None = None,
        sourceType: str = "file",
        supportsRange: bool = True,
        createdAt: int | None = None,
        title: str | None = None,
        url: str | None = None,
        fileSize: int | None = None,
        path: Path | str | None = None,
        proxies: Mapping[str, str] | None = None,
        blockNum: int | None = None,
    ) -> None:
        if config is None:
            resolvedSource = str(url or "").strip()
            if not resolvedSource:
                raise ValueError("FtpTask requires TaskConfig or url")

            config = TaskConfig(
                source=resolvedSource,
                folder=Path(path) if path is not None else Path(cfg.downloadFolder.value),
                name=sanitizeFilename(str(title or "").strip(), fallback="ftp_download"),
                proxies=_copyProxies(proxies) if proxies is not None else getProxies(),
                chunks=_normalizeChunks(blockNum),
            )

        normalizedConfig = _normalizeConfig(config)
        normalizedFiles = [
            _coerceFtpFile(rawFile, index)
            for index, rawFile in enumerate(files or [])
        ]
        self.connectionInfo = _coerceConnectionInfo(
            connectionInfo,
            normalizedConfig.source,
        )
        self.sourceType = "dir" if sourceType == "dir" else "file"
        self.createdAt = int(time_ns()) if createdAt is None else int(createdAt)
        self.url = normalizedConfig.source
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.totalBytes = _normalizeFileSize(fileSize) if fileSize is not None else 0
        self.supportsRange = bool(supportsRange)
        self.target = ""
        self._filesByIndex: dict[int, FtpTaskFile] = {}
        self._filesById: dict[str, FtpTaskFile] = {}

        resolvedStages = stages or self._buildStages(
            files=normalizedFiles,
            supportsRange=self.supportsRange,
            config=normalizedConfig,
        )

        super().__init__(
            id=id or f"ftp-task-{uuid4().hex}",
            packId=_FTP_TASK_PACK_ID,
            kind=_FTP_TASK_KIND,
            version=_FTP_TASK_VERSION,
            config=normalizedConfig,
            stages=resolvedStages,
            files=normalizedFiles,
        )
        self._rebuildFileIndexes()
        self._normalizeStageFileLinks()
        self.syncOutput()
        for stage in self.stages:
            if isinstance(stage, FtpTaskStage):
                stage.configure(self.config)
                stage.supportsRange = self.supportsRange
        self._syncFileProgress()
        self.syncStatusFromStages()

    @property
    def taskId(self) -> str:
        return self.id

    @property
    def title(self) -> str:
        return self.config.name

    @property
    def path(self) -> Path:
        return self.config.folder

    @property
    def status(self) -> LegacyTaskStatus:
        return _legacyStatus(self.state)

    @status.setter
    def status(self, value: LegacyTaskStatus | str) -> None:
        self.state = _normalizeState(value)

    @property
    def fileSize(self) -> int:
        return self.totalBytes

    @fileSize.setter
    def fileSize(self, value: int) -> None:
        self.totalBytes = _normalizeFileSize(value)

    @property
    def blockNum(self) -> int:
        return self.config.chunks

    @property
    def proxies(self) -> dict[str, str] | None:
        return None if self.config.proxies is None else dict(self.config.proxies)

    @property
    def totalFileCount(self) -> int:
        return self.fileCount

    @property
    def selectedFileCount(self) -> int:
        return self.selectedCount

    @property
    def isDirectorySource(self) -> bool:
        return self.sourceType == "dir"

    @property
    def resolvePath(self) -> str:
        return self.target

    @property
    def selectedStages(self) -> list[FtpTaskStage]:
        selectedIds = self.selectedIds
        return [
            stage
            for stage in self.stages
            if isinstance(stage, FtpTaskStage) and stage.fileId in selectedIds
        ]

    @property
    def lastError(self) -> str:
        for stage in reversed(self.stages):
            if isinstance(stage, FtpTaskStage) and stage.error:
                return stage.error
        return ""

    def _buildStages(
        self,
        *,
        files: list[FtpTaskFile],
        supportsRange: bool,
        config: TaskConfig,
    ) -> list[TaskStage]:
        return [
            FtpTaskStage(
                stageIndex=index + 1,
                fileIndex=file.index,
                fileId=file.id,
                remotePath=file.remotePath,
                fileSize=file.size,
                resolvePath="",
                supportsRange=supportsRange,
                blockNum=config.chunks,
                proxies=config.proxies,
            )
            for index, file in enumerate(files)
        ]

    def _rebuildFileIndexes(self) -> None:
        ftpFiles: list[FtpTaskFile] = []
        for index, rawFile in enumerate(self.files):
            ftpFile = _coerceFtpFile(rawFile, index)
            ftpFiles.append(ftpFile)
        self.files = ftpFiles
        self._filesByIndex = {file.index: file for file in ftpFiles}
        self._filesById = {file.id: file for file in ftpFiles}

    def _normalizeStageFileLinks(self) -> None:
        for stage in self.stages:
            if not isinstance(stage, FtpTaskStage):
                continue
            if not stage.fileId:
                stage.fileId = _fileIdForIndex(stage.fileIndex)
            file = self._filesById.get(stage.fileId) or self._filesByIndex.get(stage.fileIndex)
            if file is None:
                continue
            stage.fileIndex = file.index
            stage.fileId = file.id
            stage.remotePath = file.remotePath
            stage.fileSize = file.size

    def fileByIndex(self, index: int) -> FtpTaskFile:
        return self._filesByIndex[index]

    def syncStagePaths(self) -> None:
        self.syncOutput()

    def syncOutput(self) -> None:
        self.target = str(self.root)
        for stage in self.stages:
            if not isinstance(stage, FtpTaskStage):
                continue
            if not self.isDirectorySource:
                stage.resolvePath = self.target
                continue
            file = self._filesById.get(stage.fileId)
            relativePath = file.path if file is not None else PurePosixPath(stage.remotePath).name
            stage.resolvePath = str(
                self.root / Path(*PurePosixPath(relativePath).parts)
            )

    def setTitle(self, title: str) -> None:
        self.configure(replace(self.config, name=title))

    def _recalculateSelection(self) -> None:
        self.totalBytes = sum(file.size for file in self.files if file.selected and file.size > 0)

    def _syncFileProgress(self) -> None:
        stageByFileId = {
            stage.fileId: stage
            for stage in self.stages
            if isinstance(stage, FtpTaskStage)
        }
        for file in self.files:
            stage = stageByFileId.get(file.id)
            if stage is None:
                continue
            file.doneBytes = max(0, int(stage.doneBytes))
            file.finished = stage.state == "completed"
            if file.finished and file.size > 0:
                file.doneBytes = max(file.doneBytes, file.size)

    def select(self, ids: set[str]) -> None:
        if not ids:
            raise ValueError("至少需要选择一个文件")
        previousIds = self.selectedIds
        super().select(ids)
        if previousIds == self.selectedIds:
            return
        self._syncFileProgress()
        self.syncStatusFromStages()
        self.snapshotChanged.emit(self.snapshot())

    def updateSelectedFiles(self, selectedIndexes: set[int]) -> None:
        self.select({_fileIdForIndex(index) for index in selectedIndexes})

    def configure(self, config: TaskConfig) -> None:
        normalizedConfig = _normalizeConfig(config)
        self.connectionInfo = _coerceConnectionInfo(
            self.connectionInfo,
            normalizedConfig.source,
        )
        if normalizedConfig.source != self.config.source:
            self.connectionInfo = _connectionInfoFromSource(normalizedConfig.source)
        self.url = normalizedConfig.source
        super().configure(normalizedConfig)
        self._syncFileProgress()
        self.syncStatusFromStages()

    def applyPayloadToTask(self, payload: dict[str, Any]) -> None:
        updates: dict[str, object] = {}

        rawFolder = payload.get("path")
        if isinstance(rawFolder, (str, Path)):
            updates["folder"] = Path(rawFolder)

        if "proxies" in payload:
            rawProxies = payload.get("proxies")
            if rawProxies is None:
                updates["proxies"] = None
            elif isinstance(rawProxies, Mapping):
                updates["proxies"] = _copyProxies(cast(Mapping[str, str], rawProxies))

        rawChunks = payload.get("preBlockNum")
        if isinstance(rawChunks, int) and not isinstance(rawChunks, bool):
            updates["chunks"] = _normalizeChunks(rawChunks)

        rawName = payload.get("filename")
        if isinstance(rawName, str) and rawName.strip():
            updates["name"] = sanitizeFilename(rawName, fallback=self.config.name)

        if updates:
            self.configure(replace(self.config, **updates))

    def editForm(self, _mode: str) -> TaskForm | None:
        return TaskForm(
            title="编辑 FTP 下载任务",
            fields=(
                FormField(
                    key="name",
                    label="名称",
                    kind="text",
                    placeholder="输入输出名称",
                ),
                FormField(
                    key="folder",
                    label="下载目录",
                    kind="folder",
                    placeholder="选择输出目录",
                ),
                FormField(
                    key="files",
                    label="选择文件",
                    kind="files",
                ),
                FormField(
                    key="proxies",
                    label="代理",
                    kind="proxy",
                    note="FTP/FTPS 仅支持 socks4 或 socks5 代理；留空表示直连",
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

    def syncStatusFromStages(self) -> LegacyTaskStatus:
        self._syncFileProgress()
        selectedStages = self.selectedStages
        if not selectedStages:
            self.state = "waiting"
            self.progress = 0.0
            self.doneBytes = 0
            self.totalBytes = 0
            return self.status

        stageStates = [stage.state for stage in selectedStages]
        activeStates = {state for state in stageStates if state != "completed"}
        if "failed" in activeStates:
            self.state = "failed"
        elif not activeStates:
            self.state = "completed"
        elif "running" in activeStates:
            self.state = "running"
        elif activeStates == {"paused"}:
            self.state = "paused"
        else:
            self.state = "waiting"

        self._recalculateSelection()
        self.doneBytes = sum(stage.doneBytes for stage in selectedStages)
        if self.totalBytes > 0:
            self.progress = max(0.0, min((self.doneBytes / self.totalBytes) * 100.0, 100.0))
        else:
            self.progress = sum(stage.progress for stage in selectedStages) / len(selectedStages)
        return self.status

    def setState(self, state: str) -> None:
        normalizedState = _normalizeState(state)
        self.state = normalizedState
        self.stateChanged.emit(normalizedState)
        self.snapshotChanged.emit(self.snapshot())

    def setStatus(self, status: LegacyTaskStatus | str) -> LegacyTaskStatus:
        normalizedStatus = _normalizeState(status)
        for stage in self.selectedStages:
            if stage.state == "completed":
                continue
            if normalizedStatus == "running" and stage.state == "failed":
                stage.reset(notifyTask=False)
            stage.setStatus(normalizedStatus, emitSignals=False, notifyTask=False)
        return self.syncStatusFromStages()

    async def pause(self) -> None:
        self.setStatus("paused")

    def reset(self) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.currentStageIndex = 0
        for file in self.files:
            file.doneBytes = 0
            file.finished = False
        for stage in self.stages:
            if isinstance(stage, FtpTaskStage):
                stage.reset(notifyTask=False)
            else:
                stage.reset()
        self.syncStatusFromStages()

    def reopenForAdditionalFiles(self) -> bool:
        if self.state != "completed":
            return False

        pendingSelectedStages = [
            stage
            for stage in self.selectedStages
            if stage.state != "completed"
        ]
        if not pendingSelectedStages:
            return False

        for stage in pendingSelectedStages:
            stage.setStatus("paused", emitSignals=False, notifyTask=False)

        self.syncStatusFromStages()
        return True

    def canPause(self) -> bool:
        selectedStages = self.selectedStages
        return bool(selectedStages) and all(stage.supportsRange for stage in selectedStages)

    def stagesForExecution(self) -> list[FtpTaskStage]:
        return self.selectedStages

    async def run(self) -> None:
        currentStage: FtpTaskStage | None = None
        if self.state != "running":
            self.setState("running")

        try:
            for stage in sorted(self.selectedStages, key=lambda item: item.stageIndex):
                if self.state != "running":
                    break
                if stage.state == "completed":
                    continue
                currentStage = stage
                self.currentStageIndex = self.stages.index(stage)
                await FtpWorker(stage).run()
                self.syncStatusFromStages()
        except CancelledError:
            logger.info("{} 停止下载", self.config.name)
            raise
        except Exception as error:
            if currentStage is not None and not currentStage.error:
                currentStage.setError(error)
            logger.opt(exception=error).error("{} 下载失败", self.config.name)
            raise

        self.syncStatusFromStages()

    def snapshot(self) -> TaskSnapshot:
        return TaskSnapshot(
            id=self.id,
            packId=self.packId,
            kind=self.kind,
            name=self.config.name,
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
                "connectionInfo": _connectionInfoRecord(self.connectionInfo),
                "sourceType": self.sourceType,
                "createdAt": self.createdAt,
                "url": self.url,
                "state": self.state,
                "progress": self.progress,
                "doneBytes": self.doneBytes,
                "totalBytes": self.totalBytes,
                "supportsRange": self.supportsRange,
                "fileMetadata": [
                    {
                        "id": file.id,
                        "index": file.index,
                        "remotePath": file.remotePath,
                    }
                    for file in self.files
                    if isinstance(file, FtpTaskFile)
                ],
            }
        )
        return state

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        Task.restorePersistentState(self, state)

        rawConnectionInfo = state.get("connectionInfo")
        rawSourceType = state.get("sourceType")
        rawCreatedAt = state.get("createdAt")
        rawUrl = state.get("url")
        rawState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawTotalBytes = state.get("totalBytes")
        rawSupportsRange = state.get("supportsRange")

        self.connectionInfo = _coerceConnectionInfo(
            rawConnectionInfo if isinstance(rawConnectionInfo, Mapping) else self.connectionInfo,
            self.config.source,
        )
        if isinstance(rawSourceType, str) and rawSourceType in {"file", "dir"}:
            self.sourceType = rawSourceType
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
            self.totalBytes = max(0, rawTotalBytes)
        if isinstance(rawSupportsRange, bool):
            self.supportsRange = rawSupportsRange

        self.files = _restoreFtpFiles(state, self.stages)
        self._rebuildFileIndexes()
        self._normalizeStageFileLinks()
        self.syncOutput()
        self._syncFileProgress()
        self.syncStatusFromStages()

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
    ) -> "FtpTask":
        _ = packId
        _ = kind
        _ = version
        rawConnectionInfo = state.get("connectionInfo")
        rawSourceType = state.get("sourceType")
        rawSupportsRange = state.get("supportsRange")
        rawCreatedAt = state.get("createdAt")
        files = _restoreFtpFiles(state, stages)

        return cls(
            id=id,
            config=config,
            stages=stages,
            files=files,
            connectionInfo=rawConnectionInfo if isinstance(rawConnectionInfo, Mapping) else None,
            sourceType=rawSourceType if isinstance(rawSourceType, str) else "file",
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
class FtpSubworker:
    start: int
    progress: int
    end: int


class FtpWorker:
    def __init__(self, stage: FtpTaskStage) -> None:
        self.stage = stage
        task = getattr(stage, "_task", None)
        if not isinstance(task, FtpTask):
            raise TypeError("FtpWorker requires FtpTaskStage attached to FtpTask")
        self.task = task
        self.speedHistory: list[int] = []
        self.accelCheckTime = 0.0
        self.subworkerTasks: set[asyncio.Task[None]] = set()
        self._stopping = False

    async def _connectClient(self) -> aioftp.Client:
        return await _openClient(self.task.connectionInfo, self.stage.proxies)

    def _closeTransfer(self, client: aioftp.Client | None, stream: object) -> None:
        with suppress(Exception):
            if stream is not None:
                close = getattr(stream, "close", None)
                if callable(close):
                    _ = close()
        if client is not None:
            client.close()

    def _spawnSubworker(self, subworker: FtpSubworker) -> None:
        if self._stopping:
            return

        task = asyncio.create_task(self.handleSubworker(subworker))
        self.subworkerTasks.add(task)
        task.add_done_callback(self.subworkerTasks.discard)

    async def _cancelSubworkers(self) -> None:
        if self._stopping:
            return

        self._stopping = True
        runningTasks = tuple(task for task in self.subworkerTasks if not task.done())

        for task in runningTasks:
            task.cancel()

        if not runningTasks:
            return

        done, pending = await asyncio.wait(runningTasks, timeout=5)
        for finishedTask in done:
            with suppress(Exception, CancelledError):
                _ = finishedTask.result()

        if pending:
            logger.warning(
                "{} 仍有 {} 个 FTP 子任务未及时退出，已继续结束当前任务",
                self.stage.resolvePath,
                len(pending),
            )

    async def _waitForSubworkers(self) -> None:
        while self.subworkerTasks:
            currentTasks = tuple(self.subworkerTasks)
            done, _ = await asyncio.wait(
                currentTasks,
                return_when=asyncio.FIRST_EXCEPTION,
            )

            for finishedTask in done:
                if finishedTask.cancelled():
                    raise CancelledError

                exception = finishedTask.exception()
                if exception is not None:
                    raise exception

    def reassignSubworker(self) -> None:
        if self._stopping or self.task.state != "running" or self.stage.fileSize <= 0:
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
        newSubworker = FtpSubworker(
            slowestSubworker.end + 1,
            slowestSubworker.end + 1,
            slowestSubworker.end + base,
        )
        self.subworkers.insert(
            self.subworkers.index(slowestSubworker) + 1,
            newSubworker,
        )
        self._spawnSubworker(newSubworker)

    async def _transferRange(self, subworker: FtpSubworker) -> None:
        client = None
        stream = None
        try:
            client = await self._connectClient()
            stream = await client.download_stream(
                PurePosixPath(self.stage.remotePath),
                offset=subworker.progress,
            )

            remaining = subworker.end - subworker.progress + 1
            while remaining > 0:
                chunk = await stream.read(min(FTP_CHUNK_SIZE, remaining))
                if not chunk:
                    raise RuntimeError("FTP 数据流提前结束")
                chunkSize = len(chunk)

                await cfg.checkSpeedLimitation()
                pwrite(self.fileHandle, chunk, subworker.progress)
                subworker.progress += chunkSize
                remaining -= chunkSize
                cfg.globalSpeed += chunkSize
        finally:
            self._closeTransfer(client, stream)

    async def _transferUnknown(self, subworker: FtpSubworker) -> None:
        client = None
        stream = None
        try:
            client = await self._connectClient()
            stream = await client.download_stream(
                PurePosixPath(self.stage.remotePath),
                offset=subworker.progress,
            )

            while True:
                chunk = await stream.read(FTP_CHUNK_SIZE)
                if not chunk:
                    return
                chunkSize = len(chunk)

                await cfg.checkSpeedLimitation()
                pwrite(self.fileHandle, chunk, subworker.progress)
                subworker.progress += chunkSize
                cfg.globalSpeed += chunkSize
        finally:
            self._closeTransfer(client, stream)

    async def _transferWholeFile(self, subworker: FtpSubworker) -> None:
        client = None
        stream = None
        try:
            client = await self._connectClient()
            stream = await client.download_stream(PurePosixPath(self.stage.remotePath))

            ftruncate(self.fileHandle, 0)
            subworker.progress = 0

            while True:
                chunk = await stream.read(FTP_CHUNK_SIZE)
                if not chunk:
                    ftruncate(self.fileHandle, subworker.progress)
                    return
                chunkSize = len(chunk)

                await cfg.checkSpeedLimitation()
                pwrite(self.fileHandle, chunk, subworker.progress)
                subworker.progress += chunkSize
                cfg.globalSpeed += chunkSize
        finally:
            self._closeTransfer(client, stream)

    async def handleSubworker(self, subworker: FtpSubworker) -> None:
        if subworker.end == SpecialFileSize.UNKNOWN:
            while True:
                try:
                    await self._transferUnknown(subworker)
                    return
                except Exception as error:
                    if self._stopping or self.task.state != "running":
                        raise CancelledError from error
                    logger.opt(exception=error).error(
                        "{} 的未知大小分片 {} 连接中断，5 秒后重试",
                        self.stage.resolvePath,
                        subworker,
                    )
                    await asyncio.sleep(FTP_RETRY_DELAY)
        elif subworker.end == SpecialFileSize.NOT_SUPPORTED:
            while True:
                try:
                    await self._transferWholeFile(subworker)
                    return
                except Exception as error:
                    if self._stopping or self.task.state != "running":
                        raise CancelledError from error
                    logger.opt(exception=error).error(
                        "{} 不支持断点续传，已从头开始重试",
                        self.stage.resolvePath,
                    )
                    await asyncio.sleep(FTP_RETRY_DELAY)
        else:
            while subworker.progress <= subworker.end:
                try:
                    await self._transferRange(subworker)
                    break
                except Exception as error:
                    if self._stopping or self.task.state != "running":
                        raise CancelledError from error
                    logger.opt(exception=error).error(
                        "{} 的分片 {} 连接中断，5 秒后重试",
                        self.stage.resolvePath,
                        subworker,
                    )
                    await asyncio.sleep(FTP_RETRY_DELAY)

            if subworker.progress > subworker.end:
                subworker.progress = subworker.end + 1

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
            abs(speed - avgSpeed) / avgSpeed for speed in self.speedHistory
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
                    "FTP 自动加速已禁用，subworker 增加比: {:.2%}, 速度提升比: {:.2%}",
                    workerIncreaseRatio,
                    speedIncreaseRatio,
                )
            else:
                self.accelCheckTime = 0
                logger.info(
                    "继续 FTP 自动加速，subworker 增加比: {:.2%}, 速度提升比: {:.2%}",
                    workerIncreaseRatio,
                    speedIncreaseRatio,
                )

    async def supervisor(self) -> None:
        recordFileHandle = None
        if self.stage.supportsRange:
            recordFileHandle = open(Path(self.stage.resolvePath + ".ghd"), "wb")
        try:
            self.stage.receivedBytes = sum(
                subworker.progress - subworker.start for subworker in self.subworkers
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

                receivedBytes = sum(
                    subworker.progress - subworker.start
                    for subworker in self.subworkers
                )
                speed = receivedBytes - self.stage.receivedBytes
                progress = (
                    (receivedBytes / self.stage.fileSize) * 100.0
                    if self.stage.fileSize > 0
                    else 0.0
                )
                self.stage.updateTransfer(
                    doneBytes=receivedBytes,
                    speed=speed,
                    progress=progress,
                )

                self.checkIfAutoAcceleration()
                await asyncio.sleep(1)
        except CancelledError:
            logger.info("{} 停止下载", self.stage.resolvePath)
        except Exception as error:
            logger.opt(exception=error).error(
                "{} 的监控协程异常退出",
                self.stage.resolvePath,
            )
        finally:
            if recordFileHandle is not None:
                recordFileHandle.close()

    def restoreProgress(self) -> bool:
        recordFile = Path(self.stage.resolvePath + ".ghd")
        if not recordFile.exists():
            return False

        try:
            with open(recordFile, "rb") as file:
                while True:
                    data = file.read(24)
                    if not data:
                        break
                    start, progress, end = unpack("<QQQ", data)
                    self.subworkers.append(FtpSubworker(start, progress, end))
            return True
        except Exception as error:
            logger.opt(exception=error).error("恢复 FTP 下载分片失败 {}", self.stage.resolvePath)
            self.subworkers.clear()
            return False

    def generateSubworkers(self) -> None:
        if not self.stage.supportsRange:
            self.subworkers.append(FtpSubworker(0, 0, SpecialFileSize.NOT_SUPPORTED))
            return

        if self.stage.fileSize <= 0:
            self.subworkers.append(FtpSubworker(0, 0, SpecialFileSize.UNKNOWN))
            return

        step = self.stage.fileSize // self.stage.blockNum
        if step <= 0:
            self.subworkers.append(FtpSubworker(0, 0, max(0, self.stage.fileSize - 1)))
            return

        start = 0
        for _ in range(self.stage.blockNum - 1):
            end = start + step - 1
            self.subworkers.append(FtpSubworker(start, start, end))
            start = end + 1

        self.subworkers.append(FtpSubworker(start, start, self.stage.fileSize - 1))

    def _cleanupRecordFile(self) -> None:
        target = Path(self.stage.resolvePath + ".ghd")
        try:
            if target.is_file() or target.is_symlink():
                target.unlink()
        except Exception as error:
            logger.opt(exception=error).error("failed to cleanup temporary file {}", target)

    async def run(self) -> None:
        self.subworkers: list[FtpSubworker] = []
        self.subworkerTasks.clear()
        self._stopping = False
        shouldCleanupRecordFile = False
        Path(self.stage.resolvePath).parent.mkdir(parents=True, exist_ok=True)
        self.stage.setStatus("running")

        restored = False
        if self.stage.supportsRange:
            restored = self.restoreProgress()
        else:
            self._cleanupRecordFile()

        if not restored:
            logger.info("正在为 {} 生成 FTP 下载分片", self.stage.resolvePath)
            self.generateSubworkers()
        else:
            logger.info("从进度文件恢复 FTP 下载分片 {}", self.stage.resolvePath)

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
            for subworker in self.subworkers:
                self._spawnSubworker(subworker)

            await self._waitForSubworkers()

            self.stage.setStatus("completed")
            shouldCleanupRecordFile = True
            logger.info("{} 下载完成", self.stage.resolvePath)
        except CancelledError:
            await self._cancelSubworkers()
            self.stage.setStatus("paused")
            raise
        except Exception as error:
            await self._cancelSubworkers()
            self.stage.setError(error)
            logger.opt(exception=error).error("{} 下载阶段失败", self.stage.resolvePath)
            raise
        finally:
            if not supervisor.done():
                supervisor.cancel()
                with suppress(asyncio.CancelledError):
                    await supervisor
            self.subworkerTasks.clear()
            os.close(self.fileHandle)
            if shouldCleanupRecordFile:
                self._cleanupRecordFile()


async def _openClient(
    connectionInfo: FtpConnectionInfo,
    proxies: Mapping[str, str] | None,
) -> aioftp.Client:
    lastError: Exception | None = None
    attempts = _connectionAttempts(connectionInfo)

    for index, (port, mode) in enumerate(attempts):
        client = aioftp.Client(
            **_buildClientKwargs(proxies),
            ssl=ssl.create_default_context() if mode == "implicit" else None,
        )
        try:
            await client.connect(connectionInfo.host, port)
            if mode == "explicit":
                await client.upgrade_to_tls()
            await client.login(connectionInfo.username, connectionInfo.password)
            return client
        except Exception as error:
            client.close()
            lastError = error
            if index < len(attempts) - 1:
                logger.info(
                    "{}://{}:{} 使用 {} TLS 连接失败，尝试下一种模式: {}",
                    connectionInfo.scheme.lower(),
                    connectionInfo.host,
                    port,
                    mode,
                    repr(error),
                )

    raise lastError or RuntimeError("无法建立 FTP 连接")


async def _closeClient(client: aioftp.Client | None) -> None:
    if client is None:
        return
    try:
        await client.quit()
    except Exception:
        client.close()


def _displayTitleForSource(path: PurePosixPath, host: str) -> str:
    if path.name:
        return sanitizeFilename(path.name, fallback="ftp_download")
    return sanitizeFilename(host, fallback="ftp_download")


async def _probeRangeSupport(client: aioftp.Client) -> bool:
    try:
        await client.command("TYPE I", "200")
        await client.command("REST 1", "350")
        return True
    except Exception as error:
        logger.info("FTP 服务器不支持 REST 断点续传: {}", repr(error))
        return False


def _relativeRemotePath(remotePath: PurePosixPath, rootPath: PurePosixPath) -> str:
    try:
        return str(remotePath.relative_to(rootPath))
    except ValueError:
        return remotePath.name


def _buildTaskConfigFromPayload(payload: Mapping[str, object]) -> TaskConfig | None:
    rawSource = payload.get("url")
    if not isinstance(rawSource, str):
        return None

    source = rawSource.strip()
    if not source:
        return None

    rawFolder = payload.get("path")
    rawProxies = payload.get("proxies")
    rawChunks = payload.get("preBlockNum")
    rawName = payload.get("filename")
    return TaskConfig(
        source=source,
        folder=Path(rawFolder) if isinstance(rawFolder, (str, Path)) else Path(cfg.downloadFolder.value),
        name=rawName if isinstance(rawName, str) else "",
        proxies=(
            _copyProxies(cast(Mapping[str, str], rawProxies))
            if isinstance(rawProxies, Mapping)
            else getProxies()
        ),
        chunks=_normalizeChunks(rawChunks),
    )


async def buildFtpTask(data: TaskInput) -> FtpTask:
    inputConfig = _normalizeInputConfig(data.config)
    connectionInfo = _connectionInfoFromSource(inputConfig.source)
    sourcePath = PurePosixPath(connectionInfo.sourcePath)

    client = await _openClient(connectionInfo, inputConfig.proxies)
    try:
        sourceInfo = await client.stat(sourcePath)
        sourceType = str(sourceInfo["type"])
        if sourceType not in {"file", "dir"}:
            raise ValueError("当前 FTP 路径既不是普通文件，也不是目录")

        supportsRange = await _probeRangeSupport(client)
        files: list[FtpTaskFile] = []

        if sourceType == "file":
            preferredSize = _parsePositiveSize(data.size)
            size = preferredSize if preferredSize > 0 else _parsePositiveSize(sourceInfo.get("size"))
            files.append(
                FtpTaskFile(
                    id=_fileIdForIndex(0),
                    path=sourcePath.name or "ftp_file",
                    size=size,
                    index=0,
                    remotePath=str(sourcePath),
                )
            )
        else:
            entries = [item async for item in client.list(sourcePath, recursive=True)]
            index = 0
            for remotePath, info in entries:
                if str(info["type"]) != "file":
                    continue
                remotePosixPath = PurePosixPath(remotePath)
                files.append(
                    FtpTaskFile(
                        id=_fileIdForIndex(index),
                        path=_relativeRemotePath(remotePosixPath, sourcePath),
                        size=_parsePositiveSize(info.get("size")),
                        index=index,
                        remotePath=str(remotePosixPath),
                    )
                )
                index += 1

            if not files:
                raise ValueError("该 FTP 目录中没有可下载的普通文件")

        resolvedName = inputConfig.name or _displayTitleForSource(
            sourcePath,
            connectionInfo.host,
        )
        resolvedConfig = replace(inputConfig, name=resolvedName)
        return FtpTask(
            config=resolvedConfig,
            connectionInfo=connectionInfo,
            sourceType=sourceType,
            files=files,
            supportsRange=supportsRange,
        )
    finally:
        await _closeClient(client)


async def parse(payload: Mapping[str, object]) -> FtpTask:
    config = _buildTaskConfigFromPayload(payload)
    if config is None:
        raise ValueError("FTP 任务缺少有效的 url")
    return await buildFtpTask(TaskInput(config=config, hints=(dict(payload),)))


__all__ = [
    "FTP_CHUNK_SIZE",
    "FTP_CONNECTION_TIMEOUT",
    "FTP_DEFAULT_PORT",
    "FTP_PATH_TIMEOUT",
    "FTP_RETRY_DELAY",
    "FTP_SOCKET_TIMEOUT",
    "FTPS_DEFAULT_PORT",
    "FtpConnectionInfo",
    "FtpRemoteFile",
    "FtpSubworker",
    "FtpTask",
    "FtpTaskFile",
    "FtpTaskStage",
    "FtpWorker",
    "_buildClientKwargs",
    "_buildTaskConfigFromPayload",
    "_connectionAttempts",
    "_connectionInfoFromSource",
    "_displayTitleForSource",
    "_openClient",
    "_probeRangeSupport",
    "_relativeRemotePath",
    "buildFtpTask",
    "parse",
]
