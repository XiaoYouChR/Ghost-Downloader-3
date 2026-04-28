# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportArgumentType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportAny=false, reportExplicitAny=false, reportImplicitOverride=false, reportInconsistentConstructor=false, reportUnannotatedClassAttribute=false, reportOptionalIterable=false, reportMissingTypeArgument=false, reportUnusedCallResult=false, reportPropertyTypeMismatch=false, reportUnusedParameter=false, reportUnnecessaryComparison=false, reportUnnecessaryIsInstance=false, reportUnknownLambdaType=false, reportOptionalMemberAccess=false, reportPrivateUsage=false

from __future__ import annotations

import asyncio
import importlib
import platform
import re
import sys
from collections.abc import Mapping
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import replace
from email.message import Message
from pathlib import Path
from time import time_ns
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
from uuid import uuid4

import niquests
from loguru import logger

from app.feature_pack.api import TaskStatus
from app.feature_pack.api import FormField
from app.feature_pack.api import SingleFileTask
from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskForm
from app.feature_pack.api import TaskInput
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage
from app.supports.config import DEFAULT_HEADERS, cfg
from app.supports.utils import getProxies, sanitizeFilename, splitRequestHeadersAndCookies
from .config import m3u8Config, resolveM3U8DownloaderExecutable


_KNOWN_SUFFIXES = {
    ".m3u8",
    ".m3u",
    ".mpd",
    ".mp4",
    ".mkv",
    ".ts",
    ".webm",
    ".m4a",
    ".m4v",
    ".vtt",
    ".srt",
}
_VOD_PROGRESS_PATTERN = re.compile(
    r"(\d+)/(\d+)\s+(\d+\.\d+)%\s+(\d+\.\d+)(KB|MB|GB|B)/(\d+\.\d+)(KB|MB|GB|B)\s+(\d+\.\d+)(GBps|MBps|KBps|Bps)\s+(.+)"
)
_LIVE_PROGRESS_PATTERN = re.compile(
    r"(\d{2}m\d{2}s)/(\d{2}m\d{2}s)\s+\d+/\d+\s+(Recording|Waiting)\s+(\d+)%\s+(-|(\d+\.\d+)(GBps|MBps|KBps|Bps))"
)
_M3U8DL_RELEASE_TAG = "v0.5.1-beta"
_M3U8DL_RELEASE_API = f"https://api.github.com/repos/nilaoda/N_m3u8DL-RE/releases/tags/{_M3U8DL_RELEASE_TAG}"
_M3U8DL_RELEASE_HEADERS = {
    "accept": "application/vnd.github+json",
    "user-agent": DEFAULT_HEADERS["user-agent"],
}
_M3U8_PACK_ID = "m3u8_pack"
_M3U8_TASK_KIND = "m3u8_download"
_M3U8_STAGE_KIND = "m3u8_download"
_M3U8_INSTALL_TASK_KIND = "m3u8_install"
_M3U8_INSTALL_DOWNLOAD_STAGE_KIND = "http_download"
_M3U8_INSTALL_EXTRACT_STAGE_KIND = "extract_archive"
_M3U8_TASK_VERSION = 1
_M3U8_STAGE_VERSION = 1
_M3U8_INSTALL_TASK_VERSION = 1
_M3U8_INSTALL_STAGE_VERSION = 1
_DEFAULT_STAGE_NAME = "M3U8 下载"
M3U8_INSTALL_URL = "gd3+m3u8://install"


def _importPackModule(packId: str, moduleName: str) -> Any:
    lastError: ImportError | None = None
    candidates = (
        f"_ghost_feature_pack_{packId}.{moduleName}",
        f"{packId}.{moduleName}",
        f"features.{packId}.{moduleName}",
    )
    for candidate in candidates:
        try:
            return importlib.import_module(candidate)
        except ImportError as error:
            lastError = error

    if lastError is not None:
        raise lastError
    raise ImportError(f"无法导入 Pack 模块: {packId}.{moduleName}")


_httpTaskModule = _importPackModule("http_pack", "task")
_extractTaskModule = _importPackModule("extract_pack", "task")
_ffmpegConfigModule = _importPackModule("ffmpeg_pack", "config")
HttpTaskStage = _httpTaskModule.HttpTaskStage
HttpWorker = _httpTaskModule.HttpWorker
ExtractStage = _extractTaskModule.ExtractStage
ExtractWorker = _extractTaskModule.ExtractWorker
resolveFFmpegExecutables = _ffmpegConfigModule.resolveFFmpegExecutables


def _normalizePath(path: Path | str) -> str:
    return str(Path(path)).replace("\\", "/")


def _stripKnownSuffix(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in _KNOWN_SUFFIXES:
        return name[:-len(suffix)]
    return name


def _parseContentDispositionName(headers: dict[str, str]) -> str:
    cd = headers.get("content-disposition", "")
    if not cd:
        return ""

    msg = Message()
    msg["Content-Disposition"] = cd
    params = msg.get_params(header="Content-Disposition")
    paramDict = {key.lower(): value for key, value in params if isinstance(value, str)}

    if "filename*" in paramDict and "'" in paramDict["filename*"]:
        encoding, _, encodedText = paramDict["filename*"].split("'", 2)
        return unquote(encodedText, encoding=encoding or "utf-8")
    if "filename" in paramDict:
        return paramDict["filename"].strip("\"' ")
    return ""


def _deriveManifestType(url: str, headers: dict[str, str], body: str) -> str:
    loweredUrl = url.lower()
    contentType = headers.get("content-type", "").lower()
    sample = body.lstrip()[:256].lower()

    if ".mpd" in loweredUrl or "dash+xml" in contentType or sample.startswith("<mpd"):
        return "mpd"
    return "m3u8"


def _detectLive(manifestType: str, body: str) -> bool:
    loweredBody = body.lower()
    if manifestType == "mpd":
        return 'type="dynamic"' in loweredBody or "type='dynamic'" in loweredBody
    return "#ext-x-endlist" not in loweredBody


def _deriveDefaultTitle(url: str, headers: dict[str, str], extension: str) -> str:
    candidates: list[str] = []
    if name := _parseContentDispositionName(headers):
        candidates.append(name)

    parsedUrl = urlparse(url)
    query = parse_qs(parsedUrl.query)
    for key in ("filename", "file", "name", "title"):
        values = query.get(key)
        if values:
            candidates.append(values[0])

    if parsedUrl.path:
        candidates.append(unquote(Path(parsedUrl.path).name))

    for candidate in candidates:
        name = _stripKnownSuffix(sanitizeFilename(candidate, fallback="stream"))
        if name:
            return f"{name}.{extension}"

    return f"stream.{extension}"


def _bytesFromUnit(value: str, unit: str) -> int:
    scale = {
        "B": 1,
        "KB": 1024,
        "MB": 1024 ** 2,
        "GB": 1024 ** 3,
        "Bps": 1,
        "KBps": 1024,
        "MBps": 1024 ** 2,
        "GBps": 1024 ** 3,
    }
    return int(float(value) * scale[unit])


def _boolText(value: bool) -> str:
    return "true" if value else "false"


def _pickProxy(proxies: dict[str, object] | None) -> str:
    if not isinstance(proxies, dict):
        return ""
    for key in ("https", "http"):
        value = str(proxies.get(key) or "").strip()
        if value:
            return value
    return ""


def _copyHeaders(
    headers: Mapping[str, object] | None,
    *,
    useDefaults: bool = False,
) -> dict[str, str]:
    if headers:
        return {str(key): str(value) for key, value in headers.items()}
    if useDefaults:
        return DEFAULT_HEADERS.copy()
    return {}


def _copyProxies(
    proxies: Mapping[str, object] | None,
) -> dict[str, str] | None:
    if proxies is None:
        return None
    return {str(key): str(value) for key, value in proxies.items()}


def _normalizeThreadCount(value: int | None) -> int:
    if value is None or isinstance(value, bool):
        return max(1, int(m3u8Config.threadCount.value))
    return max(1, int(value))


def _normalizeInstallChunks(value: int | None) -> int:
    if value is None or isinstance(value, bool):
        return max(1, int(cfg.preBlockNum.value))
    return max(1, int(value))


def _copyInstallHeaders(headers: Mapping[str, object] | None) -> dict[str, str]:
    if headers:
        return {str(key): str(value) for key, value in headers.items()}
    return _M3U8DL_RELEASE_HEADERS.copy()


def _normalizeState(value: str | TaskStatus | object) -> str:
    if isinstance(value, TaskStatus):
        return value.name.lower()
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"completed", "failed", "paused", "running", "waiting"}:
            return normalized
    return "waiting"


def _legacyStatus(value: str) -> TaskStatus:
    return {
        "waiting": TaskStatus.WAITING,
        "running": TaskStatus.RUNNING,
        "paused": TaskStatus.PAUSED,
        "completed": TaskStatus.COMPLETED,
        "failed": TaskStatus.FAILED,
    }[_normalizeState(value)]


def _positiveInt(value: object, *, fallback: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return fallback
    return max(0, int(value))


def _executableName(name: str) -> str:
    return f"{name}.exe" if sys.platform == "win32" else name


def _detectRuntimeTarget() -> tuple[str, str]:
    machine = platform.machine().lower()

    if sys.platform == "win32":
        if machine in {"amd64", "x86_64"}:
            return "win-x64", "Windows x64"
        if machine in {"arm64", "aarch64"}:
            return "win-arm64", "Windows ARM64"
        return "win-NT6.0-x86", "Windows x86"

    if sys.platform == "darwin":
        if machine in {"arm64", "aarch64"}:
            return "osx-arm64", "macOS Apple Silicon"
        return "osx-x64", "macOS Intel"

    if sys.platform == "linux":
        libcName = platform.libc_ver()[0].lower()
        if machine in {"arm64", "aarch64"}:
            return ("linux-musl-arm64", "Linux musl ARM64") if libcName == "musl" else ("linux-arm64", "Linux ARM64")
        return ("linux-musl-x64", "Linux musl x64") if libcName == "musl" else ("linux-x64", "Linux x64")

    raise RuntimeError(f"当前平台暂不支持一键安装 N_m3u8DL-RE: {sys.platform}")


def _selectReleaseAsset(assets: list[dict[str, Any]]) -> dict[str, Any]:
    target, _ = _detectRuntimeTarget()
    for asset in assets:
        name = str(asset.get("name") or "")
        if target in name:
            return asset
    raise RuntimeError(f"未找到适用于当前平台的 N_m3u8DL-RE 安装包: {target}")


async def _requestReleaseAsset() -> dict[str, Any]:
    client = niquests.AsyncSession(headers=_M3U8DL_RELEASE_HEADERS, timeout=30, happy_eyeballs=True)
    client.trust_env = False

    try:
        response = await client.get(
            _M3U8DL_RELEASE_API,
            proxies=getProxies(),
            verify=cfg.SSLVerify.value,
            allow_redirects=True,
        )
        try:
            response.raise_for_status()
            payload = response.json()
        finally:
            response.close()
    finally:
        await client.close()

    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise RuntimeError("GitHub Release 返回了无效的 assets 数据")

    asset = _selectReleaseAsset(assets)
    downloadUrl = str(asset.get("browser_download_url") or "").strip()
    assetName = str(asset.get("name") or "").strip()
    size = int(asset.get("size") or 0)
    if not downloadUrl or not assetName or size <= 0:
        raise RuntimeError("GitHub Release 返回了不完整的安装包信息")

    return {
        "name": assetName,
        "url": downloadUrl,
        "size": size,
    }


def _normalizeOutputFormat(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in {"mp4", "mkv"} else str(m3u8Config.outputFormat.value)


def _normalizeM3U8Config(
    config: TaskConfig,
    *,
    outputExtension: str,
    fallbackName: str = "stream",
) -> TaskConfig:
    rawName = str(config.name).strip()
    sanitizedName = sanitizeFilename(rawName, fallback=fallbackName)
    suffix = f".{outputExtension.lower()}"
    if not sanitizedName.lower().endswith(suffix):
        sanitizedName = f"{_stripKnownSuffix(sanitizedName)}{suffix}"

    return TaskConfig(
        source=str(config.source).strip(),
        folder=Path(config.folder),
        name=sanitizedName,
        headers=_copyHeaders(config.headers, useDefaults=True),
        proxies=_copyProxies(config.proxies),
        chunks=_normalizeThreadCount(config.chunks),
    )


class M3U8TaskStage(TaskStage):
    recordTaskPackId = _M3U8_PACK_ID
    recordTaskKind = _M3U8_TASK_KIND
    recordTaskVersion = _M3U8_TASK_VERSION
    recordKind = _M3U8_STAGE_KIND
    recordVersion = _M3U8_STAGE_VERSION

    def __init__(
        self,
        *,
        id: str | None = None,
        stageIndex: int = 1,
        resolvePath: str = "",
        tempDir: str = "",
        kind: str = _M3U8_STAGE_KIND,
        version: int = _M3U8_STAGE_VERSION,
        name: str = _DEFAULT_STAGE_NAME,
        state: str | TaskStatus = "waiting",
        progress: float = 0.0,
        doneBytes: int = 0,
        speed: int = 0,
        error: str = "",
        lastMessage: str = "",
    ) -> None:
        super().__init__(
            id=id or f"m3u8-stage-{uuid4().hex}",
            kind=kind,
            version=version,
            name=name,
        )
        self.stageIndex = stageIndex
        self.resolvePath = str(resolvePath)
        self.tempDir = str(tempDir)
        self.state = _normalizeState(state)
        self.progress = max(0.0, min(float(progress), 100.0))
        self.doneBytes = max(0, int(doneBytes))
        self.speed = max(0, int(speed))
        self.error = str(error)
        self.lastMessage = str(lastMessage)

    @property
    def receivedBytes(self) -> int:
        return self.doneBytes

    @receivedBytes.setter
    def receivedBytes(self, value: int) -> None:
        self.doneBytes = max(0, int(value))

    @property
    def status(self) -> TaskStatus:
        return _legacyStatus(self.state)

    @status.setter
    def status(self, value: TaskStatus | str) -> None:
        self.setStatus(value, emitSignals=False)

    async def run(self) -> None:
        await M3U8Worker(self).run()

    def reset(self, notifyTask: bool = True) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.speed = 0
        self.error = ""
        self.lastMessage = ""
        if notifyTask:
            _notifyAttachedM3U8Task(self)
        self.stateChanged.emit(self.state)
        self.progressChanged.emit(self.progress)
        self.snapshotChanged.emit(self.snapshot())

    def setStatus(
        self,
        status: TaskStatus | str,
        *,
        emitSignals: bool = True,
        notifyTask: bool = True,
    ) -> None:
        normalizedStatus = _normalizeState(status)
        stateChanged = self.state != normalizedStatus
        progressChanged = False
        self.state = normalizedStatus

        if normalizedStatus == "completed":
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

        if notifyTask:
            _notifyAttachedM3U8Task(self)
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
        if notifyTask:
            _notifyAttachedM3U8Task(self)
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
        if notifyTask:
            _notifyAttachedM3U8Task(self)
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
            "resolvePath": self.resolvePath,
            "tempDir": self.tempDir,
            "state": self.state,
            "progress": self.progress,
            "doneBytes": self.doneBytes,
            "speed": self.speed,
            "error": self.error,
            "lastMessage": self.lastMessage,
        }

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        rawStageIndex = state.get("stageIndex")
        rawResolvePath = state.get("resolvePath")
        rawTempDir = state.get("tempDir")
        rawState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawSpeed = state.get("speed")
        rawError = state.get("error")
        rawLastMessage = state.get("lastMessage")

        if isinstance(rawStageIndex, int) and not isinstance(rawStageIndex, bool):
            self.stageIndex = rawStageIndex
        if isinstance(rawResolvePath, str):
            self.resolvePath = rawResolvePath
        if isinstance(rawTempDir, str):
            self.tempDir = rawTempDir
        if isinstance(rawState, str):
            self.state = _normalizeState(rawState)
        if isinstance(rawProgress, (int, float)) and not isinstance(rawProgress, bool):
            self.progress = max(0.0, min(float(rawProgress), 100.0))
        if isinstance(rawDoneBytes, int) and not isinstance(rawDoneBytes, bool):
            self.doneBytes = max(0, rawDoneBytes)
        if isinstance(rawSpeed, int) and not isinstance(rawSpeed, bool):
            self.speed = max(0, rawSpeed)
        if isinstance(rawError, str):
            self.error = rawError
        if isinstance(rawLastMessage, str):
            self.lastMessage = rawLastMessage

    @classmethod
    def createPersistentStage(
        cls,
        *,
        id: str,
        kind: str,
        version: int,
        name: str,
        state: Mapping[str, object],
    ) -> M3U8TaskStage:
        rawStageIndex = state.get("stageIndex")
        rawResolvePath = state.get("resolvePath")
        rawTempDir = state.get("tempDir")
        rawState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawSpeed = state.get("speed")
        rawError = state.get("error")
        rawLastMessage = state.get("lastMessage")

        return cls(
            id=id,
            kind=kind,
            version=version,
            name=name,
            stageIndex=rawStageIndex if isinstance(rawStageIndex, int) else 1,
            resolvePath=rawResolvePath if isinstance(rawResolvePath, str) else "",
            tempDir=rawTempDir if isinstance(rawTempDir, str) else "",
            state=rawState if isinstance(rawState, str) else "waiting",
            progress=float(rawProgress) if isinstance(rawProgress, (int, float)) else 0.0,
            doneBytes=rawDoneBytes if isinstance(rawDoneBytes, int) else 0,
            speed=rawSpeed if isinstance(rawSpeed, int) else 0,
            error=rawError if isinstance(rawError, str) else "",
            lastMessage=rawLastMessage if isinstance(rawLastMessage, str) else "",
        )


def _notifyAttachedM3U8Task(stage: object) -> None:
    task = getattr(stage, "_task", None)
    syncStatus = getattr(task, "syncStatusFromStages", None)
    if callable(syncStatus):
        syncStatus()


class M3U8Task(SingleFileTask):
    recordPackId = _M3U8_PACK_ID
    recordKind = _M3U8_TASK_KIND
    recordVersion = _M3U8_TASK_VERSION

    def __init__(
        self,
        *,
        id: str | None = None,
        config: TaskConfig | None = None,
        stages: list[TaskStage] | None = None,
        createdAt: int | None = None,
        title: str | None = None,
        url: str | None = None,
        fileSize: int | None = None,
        path: Path | str | None = None,
        headers: Mapping[str, object] | None = None,
        proxies: Mapping[str, object] | None = None,
        threadCount: int | None = None,
        retryCount: int | None = None,
        requestTimeout: int | None = None,
        autoSelect: bool | None = None,
        concurrentDownload: bool | None = None,
        appendUrlParams: bool | None = None,
        binaryMerge: bool | None = None,
        checkSegmentsCount: bool | None = None,
        outputFormat: str | None = None,
        liveRealTimeMerge: bool | None = None,
        liveKeepSegments: bool | None = None,
        livePipeMux: bool | None = None,
        manifestType: str = "m3u8",
        isLive: bool = False,
        actualExtension: str = "",
        state: str | TaskStatus = "waiting",
        progress: float = 0.0,
        doneBytes: int = 0,
        totalBytes: int | None = None,
        target: str = "",
    ) -> None:
        self.outputFormat = _normalizeOutputFormat(outputFormat or m3u8Config.outputFormat.value)
        self.liveRealTimeMerge = (
            bool(m3u8Config.liveRealTimeMerge.value)
            if liveRealTimeMerge is None
            else bool(liveRealTimeMerge)
        )
        self.actualExtension = str(actualExtension).strip().lstrip(".")

        if config is None:
            source = str(url or "").strip()
            if not source:
                raise ValueError("M3U8Task requires TaskConfig or url")
            config = TaskConfig(
                source=source,
                folder=Path(path) if path is not None else Path(cfg.downloadFolder.value),
                name=str(title or "stream"),
                headers=_copyHeaders(headers, useDefaults=True),
                proxies=(
                    _copyProxies(proxies)
                    if proxies is not None
                    else getProxies()
                ),
                chunks=_normalizeThreadCount(threadCount),
            )

        normalizedConfig = _normalizeM3U8Config(
            config,
            outputExtension=self.outputExtension,
            fallbackName=title or config.name or "stream",
        )
        self.threadCount = _normalizeThreadCount(normalizedConfig.chunks)
        self.retryCount = _positiveInt(retryCount, fallback=int(m3u8Config.retryCount.value))
        self.requestTimeout = _positiveInt(requestTimeout, fallback=int(m3u8Config.requestTimeout.value))
        self.autoSelect = bool(m3u8Config.autoSelect.value) if autoSelect is None else bool(autoSelect)
        self.concurrentDownload = (
            bool(m3u8Config.concurrentDownload.value)
            if concurrentDownload is None
            else bool(concurrentDownload)
        )
        self.appendUrlParams = (
            bool(m3u8Config.appendUrlParams.value)
            if appendUrlParams is None
            else bool(appendUrlParams)
        )
        self.binaryMerge = bool(m3u8Config.binaryMerge.value) if binaryMerge is None else bool(binaryMerge)
        self.checkSegmentsCount = (
            bool(m3u8Config.checkSegmentsCount.value)
            if checkSegmentsCount is None
            else bool(checkSegmentsCount)
        )
        self.liveKeepSegments = (
            bool(m3u8Config.liveKeepSegments.value)
            if liveKeepSegments is None
            else bool(liveKeepSegments)
        )
        self.livePipeMux = bool(m3u8Config.livePipeMux.value) if livePipeMux is None else bool(livePipeMux)
        self.manifestType = "mpd" if manifestType == "mpd" else "m3u8"
        self.isLive = bool(isLive)
        self.createdAt = int(time_ns()) if createdAt is None else int(createdAt)
        self.state = _normalizeState(state)
        self.progress = max(0.0, min(float(progress), 100.0))
        self.doneBytes = max(0, int(doneBytes))
        self.totalBytes = max(0, int(totalBytes if totalBytes is not None else (fileSize or 0)))
        self.target = str(target)

        resolvedStages = stages or [M3U8TaskStage(stageIndex=1)]
        super().__init__(
            id=id or f"m3u8-task-{uuid4().hex}",
            packId=_M3U8_PACK_ID,
            kind=_M3U8_TASK_KIND,
            version=_M3U8_TASK_VERSION,
            config=normalizedConfig,
            stages=resolvedStages,
        )
        self.syncOutput()
        self.syncStatusFromStages()

    @property
    def taskId(self) -> str:
        return self.id

    @property
    def title(self) -> str:
        return self.filename

    @title.setter
    def title(self, value: str) -> None:
        self.setTitle(value)

    @property
    def url(self) -> str:
        return self.config.source

    @url.setter
    def url(self, value: str) -> None:
        self.configure(replace(self.config, source=str(value).strip()))

    @property
    def status(self) -> TaskStatus:
        return _legacyStatus(self.state)

    @property
    def fileSize(self) -> int:
        return self.totalBytes

    @fileSize.setter
    def fileSize(self, value: int) -> None:
        self.totalBytes = max(0, int(value))

    @property
    def headers(self) -> dict[str, str]:
        return dict(self.config.headers)

    @headers.setter
    def headers(self, value: Mapping[str, object]) -> None:
        self.configure(replace(self.config, headers=_copyHeaders(value, useDefaults=True)))

    @property
    def proxies(self) -> dict[str, str] | None:
        return _copyProxies(self.config.proxies)

    @proxies.setter
    def proxies(self, value: Mapping[str, object] | None) -> None:
        self.configure(replace(self.config, proxies=_copyProxies(value)))

    @property
    def outputExtension(self) -> str:
        if self.actualExtension:
            return self.actualExtension
        if self.liveRealTimeMerge:
            return "ts"
        return self.outputFormat

    @property
    def saveName(self) -> str:
        suffix = f".{self.outputExtension.lower()}"
        if self.filename.lower().endswith(suffix):
            return self.filename[:-len(suffix)]
        return _stripKnownSuffix(self.filename)

    @property
    def tempDir(self) -> str:
        return _normalizePath(self.folder / ".gd3_m3u8" / self.taskId)

    @property
    def resolvePath(self) -> str:
        return self.target or _normalizePath(self.path)

    @property
    def lastError(self) -> str:
        for stage in reversed(self.stages):
            error = getattr(stage, "error", "")
            if isinstance(error, str) and error:
                return error
        return ""

    def setTitle(self, title: str) -> None:
        self.rename(self._normalizeTitle(title))

    def _normalizeTitle(self, title: str) -> str:
        return _normalizeM3U8Config(
            replace(self.config, name=title),
            outputExtension=self.outputExtension,
            fallbackName=self.filename or "stream",
        ).name

    def syncOutput(self) -> None:
        self.target = _normalizePath(self.path)
        tempDir = self.tempDir
        for stage in self.stages:
            if isinstance(stage, M3U8TaskStage):
                stage.resolvePath = self.target
                stage.tempDir = tempDir

    def configure(self, config: TaskConfig) -> None:
        normalizedConfig = _normalizeM3U8Config(
            config,
            outputExtension=self.outputExtension,
            fallbackName=self.filename or "stream",
        )
        self.threadCount = _normalizeThreadCount(normalizedConfig.chunks)
        super().configure(normalizedConfig)
        self.syncStatusFromStages()

    def editForm(self, _mode: str) -> TaskForm | None:
        return TaskForm(
            title="编辑流媒体下载任务",
            fields=(
                FormField(
                    key="source",
                    label="来源",
                    kind="text",
                    placeholder="输入 M3U8 或 MPD 地址",
                ),
                FormField(
                    key="name",
                    label="输出文件名",
                    kind="text",
                    placeholder="输入输出文件名",
                ),
                FormField(
                    key="folder",
                    label="输出目录",
                    kind="folder",
                    placeholder="选择输出目录",
                ),
                FormField(
                    key="headers",
                    label="请求头",
                    kind="headers",
                    placeholder="Referer: https://example.com",
                ),
                FormField(
                    key="proxies",
                    label="代理",
                    kind="proxy",
                    placeholder="https: http://127.0.0.1:7890",
                ),
                FormField(
                    key="chunks",
                    label="下载线程数",
                    kind="int",
                    min=1,
                    max=64,
                ),
            ),
        )

    def setState(self, state: TaskStatus | str) -> TaskStatus:
        normalizedState = _normalizeState(state)
        self.state = normalizedState
        for stage in self.stages:
            if isinstance(stage, M3U8TaskStage):
                if normalizedState == "running" and stage.state == "failed":
                    stage.reset(notifyTask=False)
                if stage.state != "completed":
                    stage.setStatus(normalizedState, emitSignals=False, notifyTask=False)
        self.syncStatusFromStages()
        self.stateChanged.emit(self.state)
        self.snapshotChanged.emit(self.snapshot())
        return self.status

    def setStatus(self, status: TaskStatus | str) -> TaskStatus:
        return self.setState(status)

    def syncStatusFromStages(self) -> TaskStatus:
        if not self.stages:
            return self.status

        states = [_normalizeState(getattr(stage, "state", "waiting")) for stage in self.stages]
        if any(state == "failed" for state in states):
            self.state = "failed"
        elif all(state == "completed" for state in states):
            self.state = "completed"
        elif any(state == "running" for state in states):
            self.state = "running"
        elif all(state == "paused" for state in states):
            self.state = "paused"
        else:
            self.state = "waiting"

        if self.stages:
            self.progress = sum(float(getattr(stage, "progress", 0.0)) for stage in self.stages) / len(self.stages)
            self.doneBytes = sum(int(getattr(stage, "doneBytes", 0)) for stage in self.stages)
        return self.status

    def canPause(self) -> bool:
        return bool(self.stages) and all(stage.canPause() for stage in self.stages)

    async def pause(self) -> None:
        self.setState("paused")

    async def run(self) -> None:
        currentStage: TaskStage | None = None
        if self.state != "running":
            self.setState("running")

        try:
            for stage in sorted(self.stages, key=lambda item: int(getattr(item, "stageIndex", 0))):
                if self.state != "running":
                    break
                if _normalizeState(getattr(stage, "state", "waiting")) == "completed":
                    continue

                currentStage = stage
                self.currentStageIndex = self.stages.index(stage)
                if isinstance(stage, M3U8TaskStage):
                    await M3U8Worker(stage).run()
                    self.syncStatusFromStages()
                    continue

                raise TypeError(f"不支持的 M3U8TaskStage: {type(stage).__name__}")
        except asyncio.CancelledError:
            logger.info("{} 停止下载", self.title)
            self.syncStatusFromStages()
            raise
        except Exception as error:
            setError = getattr(currentStage, "setError", None)
            if currentStage is not None and callable(setError) and not getattr(currentStage, "error", ""):
                setError(error)
            self.syncStatusFromStages()
            logger.opt(exception=error).error("{} 下载失败", self.title)
            raise

        self.syncStatusFromStages()

    def reset(self) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.currentStageIndex = 0
        for stage in self.stages:
            if isinstance(stage, M3U8TaskStage):
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
                "state": self.state,
                "progress": self.progress,
                "doneBytes": self.doneBytes,
                "totalBytes": self.totalBytes,
                "target": self.target,
                "retryCount": self.retryCount,
                "requestTimeout": self.requestTimeout,
                "autoSelect": self.autoSelect,
                "concurrentDownload": self.concurrentDownload,
                "appendUrlParams": self.appendUrlParams,
                "binaryMerge": self.binaryMerge,
                "checkSegmentsCount": self.checkSegmentsCount,
                "outputFormat": self.outputFormat,
                "liveRealTimeMerge": self.liveRealTimeMerge,
                "liveKeepSegments": self.liveKeepSegments,
                "livePipeMux": self.livePipeMux,
                "manifestType": self.manifestType,
                "isLive": self.isLive,
                "actualExtension": self.actualExtension,
            }
        )
        return state

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        super().restorePersistentState(state)
        rawCreatedAt = state.get("createdAt")
        rawState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawTotalBytes = state.get("totalBytes")
        rawTarget = state.get("target")
        rawRetryCount = state.get("retryCount")
        rawRequestTimeout = state.get("requestTimeout")
        rawOutputFormat = state.get("outputFormat")
        rawManifestType = state.get("manifestType")
        rawActualExtension = state.get("actualExtension")

        if isinstance(rawCreatedAt, int) and not isinstance(rawCreatedAt, bool):
            self.createdAt = rawCreatedAt
        if isinstance(rawState, str):
            self.state = _normalizeState(rawState)
        if isinstance(rawProgress, (int, float)) and not isinstance(rawProgress, bool):
            self.progress = max(0.0, min(float(rawProgress), 100.0))
        if isinstance(rawDoneBytes, int) and not isinstance(rawDoneBytes, bool):
            self.doneBytes = max(0, rawDoneBytes)
        if isinstance(rawTotalBytes, int) and not isinstance(rawTotalBytes, bool):
            self.totalBytes = max(0, rawTotalBytes)
        if isinstance(rawTarget, str) and rawTarget.strip():
            self.target = rawTarget
        if isinstance(rawRetryCount, int) and not isinstance(rawRetryCount, bool):
            self.retryCount = max(0, rawRetryCount)
        if isinstance(rawRequestTimeout, int) and not isinstance(rawRequestTimeout, bool):
            self.requestTimeout = max(1, rawRequestTimeout)
        if isinstance(rawOutputFormat, str):
            self.outputFormat = _normalizeOutputFormat(rawOutputFormat)
        if isinstance(rawManifestType, str):
            self.manifestType = "mpd" if rawManifestType == "mpd" else "m3u8"
        if isinstance(rawActualExtension, str):
            self.actualExtension = rawActualExtension.strip().lstrip(".")

        for key in (
            "autoSelect",
            "concurrentDownload",
            "appendUrlParams",
            "binaryMerge",
            "checkSegmentsCount",
            "liveRealTimeMerge",
            "liveKeepSegments",
            "livePipeMux",
            "isLive",
        ):
            value = state.get(key)
            if isinstance(value, bool):
                setattr(self, key, value)

        self.threadCount = _normalizeThreadCount(self.config.chunks)
        self.syncOutput()
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
    ) -> M3U8Task:
        _ = packId
        _ = kind
        _ = version
        rawCreatedAt = state.get("createdAt")
        rawTotalBytes = state.get("totalBytes")

        return cls(
            id=id,
            config=config,
            stages=stages,
            createdAt=rawCreatedAt if isinstance(rawCreatedAt, int) else None,
            totalBytes=rawTotalBytes if isinstance(rawTotalBytes, int) else 0,
            retryCount=state.get("retryCount") if isinstance(state.get("retryCount"), int) else None,
            requestTimeout=state.get("requestTimeout") if isinstance(state.get("requestTimeout"), int) else None,
            autoSelect=state.get("autoSelect") if isinstance(state.get("autoSelect"), bool) else None,
            concurrentDownload=state.get("concurrentDownload") if isinstance(state.get("concurrentDownload"), bool) else None,
            appendUrlParams=state.get("appendUrlParams") if isinstance(state.get("appendUrlParams"), bool) else None,
            binaryMerge=state.get("binaryMerge") if isinstance(state.get("binaryMerge"), bool) else None,
            checkSegmentsCount=state.get("checkSegmentsCount") if isinstance(state.get("checkSegmentsCount"), bool) else None,
            outputFormat=state.get("outputFormat") if isinstance(state.get("outputFormat"), str) else None,
            liveRealTimeMerge=state.get("liveRealTimeMerge") if isinstance(state.get("liveRealTimeMerge"), bool) else None,
            liveKeepSegments=state.get("liveKeepSegments") if isinstance(state.get("liveKeepSegments"), bool) else None,
            livePipeMux=state.get("livePipeMux") if isinstance(state.get("livePipeMux"), bool) else None,
            manifestType=state.get("manifestType") if isinstance(state.get("manifestType"), str) else "m3u8",
            isLive=bool(state.get("isLive")) if isinstance(state.get("isLive"), bool) else False,
            actualExtension=state.get("actualExtension") if isinstance(state.get("actualExtension"), str) else "",
        )

    def __hash__(self) -> int:
        return hash(self.id)


class M3U8Worker:
    def __init__(self, stage: M3U8TaskStage):
        super().__init__(stage)
        self.stage = stage
        self.task: M3U8Task = getattr(stage, "_task")

    def _buildArguments(self, downloaderPath: str) -> list[str]:
        args = [
            self.task.url,
            f"--save-dir={_normalizePath(self.task.folder)}",
            f"--save-name={self.task.saveName}",
            f"--tmp-dir={self.stage.tempDir}",
            f"--thread-count={self.task.threadCount}",
            f"--download-retry-count={self.task.retryCount}",
            f"--http-request-timeout={self.task.requestTimeout}",
            f"--auto-select={_boolText(self.task.autoSelect)}",
            f"--concurrent-download={_boolText(self.task.concurrentDownload)}",
            f"--append-url-params={_boolText(self.task.appendUrlParams)}",
            f"--binary-merge={_boolText(self.task.binaryMerge)}",
            f"--check-segments-count={_boolText(self.task.checkSegmentsCount)}",
            "--del-after-done=true",
            "--write-meta-json=false",
            "--no-log=true",
            "--no-ansi-color=true",
            "--disable-update-check=true",
        ]

        proxyUrl = _pickProxy(self.task.proxies)
        args.append("--use-system-proxy=false")
        if proxyUrl:
            args.append(f"--custom-proxy={proxyUrl}")

        ffmpegPath, _ = resolveFFmpegExecutables()
        if ffmpegPath:
            args.append(f"--ffmpeg-binary-path={ffmpegPath}")

        if self.task.liveRealTimeMerge:
            args.append("--live-real-time-merge=true")
            args.append(f"--live-keep-segments={_boolText(self.task.liveKeepSegments)}")
            args.append(f"--live-pipe-mux={_boolText(self.task.livePipeMux)}")
        else:
            muxOption = f"format={self.task.outputFormat}:muxer=ffmpeg"
            if ffmpegPath:
                muxOption += f":bin_path={ffmpegPath}"
            args.append(f"--mux-after-done={muxOption}")

        for name, value in self.task.headers.items():
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            args.extend(["-H", f"{name}: {text}"])

        return args

    def _handleOutputLine(self, line: str):
        text = line.strip()
        if not text:
            return

        self.stage.lastMessage = text[:1000]

        vodMatch = _VOD_PROGRESS_PATTERN.search(text)
        if vodMatch:
            progress = float(vodMatch.group(3))
            currentSize = _bytesFromUnit(vodMatch.group(4), vodMatch.group(5))
            totalSize = _bytesFromUnit(vodMatch.group(6), vodMatch.group(7))
            speed = _bytesFromUnit(vodMatch.group(8), vodMatch.group(9))
            if totalSize > 0:
                self.task.fileSize = totalSize
            self.stage.updateTransfer(
                doneBytes=currentSize,
                speed=speed,
                progress=progress,
            )
            return

        liveMatch = _LIVE_PROGRESS_PATTERN.search(text)
        if liveMatch:
            self.stage.updateTransfer(
                doneBytes=self.stage.doneBytes,
                speed=0 if liveMatch.group(5) == "-" else _bytesFromUnit(liveMatch.group(6), liveMatch.group(7)),
                progress=float(liveMatch.group(4)),
            )

    async def _readOutput(self, stream: asyncio.StreamReader | None):
        if stream is None:
            return

        buffer = ""
        while True:
            chunk = await stream.read(4096)
            if not chunk:
                break

            buffer += chunk.decode("utf-8", errors="ignore")
            buffer = buffer.replace("\r\n", "\n").replace("\r", "\n")
            lines = buffer.split("\n")
            buffer = lines.pop()
            for line in lines:
                self._handleOutputLine(line)

        if buffer.strip():
            self._handleOutputLine(buffer)

    def _resolveFinalOutput(self) -> Path | None:
        target = Path(self.stage.resolvePath)
        if target.is_file():
            return target

        outputDir = self.task.folder
        if not outputDir.is_dir():
            return None

        candidates: list[Path] = []
        expectedSuffix = f".{self.task.outputExtension.lower()}"
        prefix = self.task.saveName.lower()
        ignoredSuffixes = {".json", ".txt", ".log", ".tmp", ".ghd"}

        for candidate in outputDir.iterdir():
            if not candidate.is_file():
                continue
            if candidate.suffix.lower() in ignoredSuffixes:
                continue
            if not candidate.name.lower().startswith(prefix):
                continue
            candidates.append(candidate)

        if not candidates:
            return None

        candidates.sort(
            key=lambda path: (
                path.suffix.lower() != expectedSuffix,
                -path.stat().st_mtime,
            )
        )
        return candidates[0]

    def _syncFinalOutput(self):
        candidate = self._resolveFinalOutput()
        if candidate is None:
            return

        self.task.actualExtension = candidate.suffix.lstrip(".")
        self.task.fileSize = max(self.task.fileSize, candidate.stat().st_size)
        if candidate.name != self.task.title:
            self.task.setTitle(candidate.name)

    async def _stopProcess(self, process: asyncio.subprocess.Process):
        if process.returncode is not None:
            return

        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=3)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

    async def run(self):
        downloaderPath = resolveM3U8DownloaderExecutable()
        if not downloaderPath:
            self.stage.setStatus(TaskStatus.FAILED)
            raise RuntimeError("未找到可用的 N_m3u8DL-RE，请先在设置中安装或配置运行时")

        self.task.folder.mkdir(parents=True, exist_ok=True)
        Path(self.stage.tempDir).mkdir(parents=True, exist_ok=True)

        process = None
        outputTask = None
        try:
            args = self._buildArguments(downloaderPath)
            process = await asyncio.create_subprocess_exec(
                downloaderPath,
                *args,
                cwd=str(Path(downloaderPath).parent),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            outputTask = asyncio.create_task(self._readOutput(process.stdout))

            await process.wait()
            if outputTask is not None:
                await outputTask

            if process.returncode != 0:
                message = self.stage.lastMessage or f"N_m3u8DL-RE 退出码异常: {process.returncode}"
                raise RuntimeError(message)

            self._syncFinalOutput()
            self.stage.setStatus(TaskStatus.COMPLETED)
        except asyncio.CancelledError:
            self.stage.setStatus(TaskStatus.PAUSED)
            if process is not None:
                await self._stopProcess(process)
            if outputTask is not None and not outputTask.done():
                outputTask.cancel()
                with suppress(asyncio.CancelledError):
                    await outputTask
            raise
        except Exception as e:
            self.stage.setError(e)
            raise


async def buildM3U8Task(data: TaskInput) -> M3U8Task:
    url = str(data.config.source).strip()
    headers = _copyHeaders(data.config.headers, useDefaults=True)
    proxies = _copyProxies(data.config.proxies) if data.config.proxies is not None else getProxies()
    requestHeaders, requestCookies = splitRequestHeadersAndCookies(headers)

    client = niquests.AsyncSession(timeout=30, happy_eyeballs=True)
    client.trust_env = False

    try:
        response = await client.get(
            url,
            headers=requestHeaders,
            cookies=requestCookies,
            proxies=proxies,
            verify=cfg.SSLVerify.value,
            allow_redirects=True,
        )
        try:
            response.raise_for_status()
            body = response.text
            loweredHeaders = {key.lower(): value for key, value in response.headers.items()}
            manifestType = _deriveManifestType(str(response.url), loweredHeaders, body)
            isLive = _detectLive(manifestType, body)
            title = _deriveDefaultTitle(
                str(response.url),
                loweredHeaders,
                "ts" if m3u8Config.liveRealTimeMerge.value else m3u8Config.outputFormat.value,
            )
        finally:
            response.close()
    finally:
        await client.close()

    requestedName = str(data.config.name).strip()
    resolvedTitle = requestedName or title
    normalizedConfig = TaskConfig(
        source=url,
        folder=Path(data.config.folder),
        name=resolvedTitle,
        headers=headers,
        proxies=proxies,
        chunks=_normalizeThreadCount(data.config.chunks),
    )
    size = data.size if isinstance(data.size, int) and not isinstance(data.size, bool) else 0
    task = M3U8Task(
        config=normalizedConfig,
        totalBytes=max(0, size),
        threadCount=m3u8Config.threadCount.value,
        retryCount=m3u8Config.retryCount.value,
        requestTimeout=m3u8Config.requestTimeout.value,
        autoSelect=m3u8Config.autoSelect.value,
        concurrentDownload=m3u8Config.concurrentDownload.value,
        appendUrlParams=m3u8Config.appendUrlParams.value,
        binaryMerge=m3u8Config.binaryMerge.value,
        checkSegmentsCount=m3u8Config.checkSegmentsCount.value,
        outputFormat=m3u8Config.outputFormat.value,
        liveRealTimeMerge=m3u8Config.liveRealTimeMerge.value,
        liveKeepSegments=m3u8Config.liveKeepSegments.value,
        livePipeMux=m3u8Config.livePipeMux.value,
        manifestType=manifestType,
        isLive=isLive,
    )
    return task


class M3U8InstallDownloadStage(HttpTaskStage):
    recordTaskPackId = _M3U8_PACK_ID
    recordTaskKind = _M3U8_INSTALL_TASK_KIND
    recordTaskVersion = _M3U8_INSTALL_TASK_VERSION
    recordKind = _M3U8_INSTALL_DOWNLOAD_STAGE_KIND
    recordVersion = _M3U8_INSTALL_STAGE_VERSION

    async def run(self) -> None:
        await super().run()

    def reset(self) -> None:
        super().reset()

    def snapshot(self) -> StageSnapshot:
        return super().snapshot()


class M3U8InstallExtractStage(ExtractStage):
    recordTaskPackId = _M3U8_PACK_ID
    recordTaskKind = _M3U8_INSTALL_TASK_KIND
    recordTaskVersion = _M3U8_INSTALL_TASK_VERSION
    recordKind = _M3U8_INSTALL_EXTRACT_STAGE_KIND
    recordVersion = _M3U8_INSTALL_STAGE_VERSION

    def configure(self, config: TaskConfig) -> None:
        self.installFolder = _normalizePath(Path(config.folder))

    async def run(self) -> None:
        await super().run()

    def reset(self) -> None:
        super().reset()

    def snapshot(self) -> StageSnapshot:
        return super().snapshot()


class M3U8InstallTask(Task):
    recordPackId = _M3U8_PACK_ID
    recordKind = _M3U8_INSTALL_TASK_KIND
    recordVersion = _M3U8_INSTALL_TASK_VERSION

    def __init__(
        self,
        *,
        id: str | None = None,
        config: TaskConfig,
        title: str,
        assetName: str,
        archiveSize: int,
        stages: list[TaskStage] | None = None,
        executablePath: str = "",
        createdAt: int | None = None,
        state: str | TaskStatus = "waiting",
        progress: float = 0.0,
        doneBytes: int = 0,
        totalBytes: int | None = None,
        target: str = "",
    ) -> None:
        self.title = str(title).strip() or "N_m3u8DL-RE 安装"
        self.assetName = str(assetName).strip() or Path(config.name).name or "N_m3u8DL-RE.zip"
        self.archiveSize = max(0, int(archiveSize))
        self.executablePath = str(executablePath).strip()
        self.createdAt = int(time_ns()) if createdAt is None else int(createdAt)
        self.state = _normalizeState(state)
        self.progress = max(0.0, min(float(progress), 100.0))
        self.doneBytes = max(0, int(doneBytes))
        self.totalBytes = max(
            self.archiveSize,
            int(totalBytes) if isinstance(totalBytes, int) and not isinstance(totalBytes, bool) else self.archiveSize,
        )
        self.target = str(target).strip()
        normalizedConfig = self._normalizeConfig(config, assetName=self.assetName)
        resolvedStages = stages or self._buildStages(normalizedConfig)

        super().__init__(
            id=id or f"m3u8-install-task-{uuid4().hex}",
            packId=_M3U8_PACK_ID,
            kind=_M3U8_INSTALL_TASK_KIND,
            version=_M3U8_INSTALL_TASK_VERSION,
            config=normalizedConfig,
            stages=resolvedStages,
        )
        self.syncOutput()
        self.syncStatusFromStages()

    @staticmethod
    def _normalizeConfig(config: TaskConfig, *, assetName: str) -> TaskConfig:
        return TaskConfig(
            source=str(config.source).strip(),
            folder=Path(config.folder),
            name=str(config.name).strip() or assetName,
            headers=_copyInstallHeaders(config.headers),
            proxies=_copyProxies(config.proxies),
            chunks=_normalizeInstallChunks(config.chunks),
        )

    def _buildStages(self, config: TaskConfig) -> list[TaskStage]:
        return [
            M3U8InstallDownloadStage(
                id=f"m3u8-install-download-{uuid4().hex}",
                stageIndex=1,
                url=config.source,
                fileSize=self.archiveSize,
                headers=config.headers,
                proxies=config.proxies,
                resolvePath="",
                blockNum=config.chunks,
                supportsRange=True,
                kind=_M3U8_INSTALL_DOWNLOAD_STAGE_KIND,
                version=_M3U8_INSTALL_STAGE_VERSION,
                name="下载 N_m3u8DL-RE",
            ),
            M3U8InstallExtractStage(
                id=f"m3u8-install-extract-{uuid4().hex}",
                stageIndex=2,
                archivePath="",
                installFolder=_normalizePath(config.folder),
                executableNames=[_executableName("N_m3u8DL-RE")],
                cleanupArchive=True,
                kind=_M3U8_INSTALL_EXTRACT_STAGE_KIND,
                version=_M3U8_INSTALL_STAGE_VERSION,
                name="解压 N_m3u8DL-RE",
            ),
        ]

    @property
    def taskId(self) -> str:
        return self.id

    @property
    def status(self) -> TaskStatus:
        return _legacyStatus(self.state)

    @property
    def installFolder(self) -> Path:
        return Path(self.config.folder)

    @property
    def archivePath(self) -> str:
        return _normalizePath(self.installFolder / self.assetName)

    @property
    def fileSize(self) -> int:
        return self.totalBytes

    @fileSize.setter
    def fileSize(self, value: int) -> None:
        self.totalBytes = max(0, int(value))

    @property
    def resolvePath(self) -> str:
        return self.executablePath or self.archivePath

    def downloadStage(self) -> M3U8InstallDownloadStage:
        stage = self.stages[0]
        if not isinstance(stage, M3U8InstallDownloadStage):
            raise TypeError(
                f"Unexpected M3U8 install download stage type: {type(stage).__name__}"
            )
        return stage

    def extractStage(self) -> M3U8InstallExtractStage:
        stage = self.stages[1]
        if not isinstance(stage, M3U8InstallExtractStage):
            raise TypeError(
                f"Unexpected M3U8 install extract stage type: {type(stage).__name__}"
            )
        return stage

    def configure(self, config: TaskConfig) -> None:
        normalizedConfig = self._normalizeConfig(config, assetName=self.assetName)
        self.assetName = normalizedConfig.name
        super().configure(normalizedConfig)
        self.syncStatusFromStages()

    def editForm(self, _mode: str) -> TaskForm | None:
        return TaskForm(
            title="编辑 N_m3u8DL-RE 安装任务",
            fields=(
                FormField(
                    key="folder",
                    label="安装目录",
                    kind="folder",
                    placeholder="选择安装目录",
                ),
                FormField(
                    key="proxies",
                    label="代理",
                    kind="proxy",
                    placeholder="https: http://127.0.0.1:7890",
                ),
                FormField(
                    key="chunks",
                    label="下载线程数",
                    kind="int",
                    min=1,
                    max=64,
                ),
            ),
        )

    def syncOutput(self) -> None:
        self.target = _normalizePath(self.installFolder)
        downloadStage = self.downloadStage()
        extractStage = self.extractStage()

        downloadStage.resolvePath = self.archivePath
        downloadStage.fileSize = self.archiveSize
        extractStage.archivePath = self.archivePath
        extractStage.installFolder = self.target

        self._syncResolvedExecutable()

    def _syncResolvedExecutable(self) -> None:
        executableName = _executableName("N_m3u8DL-RE")
        extractedExecutable = self.extractStage().extractedExecutables.get(executableName)
        if extractedExecutable:
            self.executablePath = extractedExecutable
            return

        self.executablePath = _normalizePath(self.installFolder / executableName)

    def syncStatusFromStages(self) -> TaskStatus:
        stageSnapshots = tuple(stage.snapshot() for stage in self.stages)
        if not stageSnapshots:
            return self.status

        normalizedStates = [snapshot.state for snapshot in stageSnapshots]
        if any(state == "failed" for state in normalizedStates):
            self.state = "failed"
        elif all(state == "completed" for state in normalizedStates):
            self.state = "completed"
        elif any(state == "running" for state in normalizedStates):
            self.state = "running"
        elif all(state == "paused" for state in normalizedStates):
            self.state = "paused"
        else:
            self.state = "waiting"

        self.progress = self._projectProgress(stageSnapshots)
        self.doneBytes = self._projectDoneBytes(stageSnapshots)
        self.totalBytes = max(self.totalBytes, self.archiveSize, self.doneBytes)
        return self.status

    def setStatus(self, status: TaskStatus | str) -> TaskStatus:
        normalizedStatus = _normalizeState(status)
        if not self.stages:
            self.state = normalizedStatus
            return self.status

        for stage in self.stages:
            currentSetter = getattr(stage, "setStatus", None)
            if callable(currentSetter):
                currentSetter(normalizedStatus, emitSignals=False, notifyTask=False)
                continue
            if normalizedStatus == "paused":
                stage.reset()
        return self.syncStatusFromStages()

    def occupiesDownloadSlot(self) -> bool:
        return self.state == "running"

    def willOccupyDownloadSlotWhenStarted(self) -> bool:
        return True

    def _projectProgress(self, stageSnapshots: Sequence[object]) -> float:
        if not stageSnapshots:
            return self.progress

        currentIndex = min(self.currentStageIndex, len(stageSnapshots) - 1)
        currentSnapshot = stageSnapshots[currentIndex]
        if not hasattr(currentSnapshot, "progress") or not hasattr(currentSnapshot, "state"):
            return self.progress

        currentProgress = max(0.0, min(float(getattr(currentSnapshot, "progress", 0.0)), 100.0))
        currentState = _normalizeState(getattr(currentSnapshot, "state", "waiting"))
        if currentState == "completed":
            completedStages = currentIndex + 1
            currentProgress = 0.0
        else:
            completedStages = currentIndex
        return ((completedStages + currentProgress / 100.0) / len(stageSnapshots)) * 100.0

    def _projectDoneBytes(self, stageSnapshots: Sequence[object]) -> int:
        if not stageSnapshots:
            return self.doneBytes

        currentIndex = min(self.currentStageIndex, len(stageSnapshots) - 1)
        currentSnapshot = stageSnapshots[currentIndex]
        return max(0, int(getattr(currentSnapshot, "doneBytes", 0)))

    async def run(self) -> None:
        currentStage: TaskStage | None = None
        try:
            for stage in self.iterStages():
                self.currentStageIndex = self.stages.index(stage)
                stageState = _normalizeState(getattr(stage, "state", "waiting"))
                if stageState == "completed":
                    continue

                currentStage = stage
                self.state = "running"
                if isinstance(stage, M3U8InstallDownloadStage):
                    await HttpWorker(stage).run()
                    self.syncStatusFromStages()
                    continue
                if isinstance(stage, M3U8InstallExtractStage):
                    await ExtractWorker(stage).run()
                    self._syncResolvedExecutable()
                    self.syncStatusFromStages()
                    continue

                raise TypeError(f"不支持的 M3U8InstallTaskStage: {type(stage).__name__}")
        except asyncio.CancelledError:
            logger.info("{} 停止安装", self.title)
            self.syncStatusFromStages()
            raise
        except Exception as error:
            setError = getattr(currentStage, "setError", None)
            if currentStage is not None and callable(setError) and not getattr(currentStage, "error", ""):
                setError(error)
            self.syncStatusFromStages()
            logger.opt(exception=error).error("{} 安装失败", self.title)
            raise
        finally:
            self._syncResolvedExecutable()
            self.syncStatusFromStages()

    def reset(self) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.currentStageIndex = 0
        self.totalBytes = max(self.totalBytes, self.archiveSize)
        for stage in self.stages:
            stage.reset()
        self._syncResolvedExecutable()
        self.syncStatusFromStages()

    def snapshot(self) -> TaskSnapshot:
        return TaskSnapshot(
            id=self.id,
            packId=self.packId,
            kind=self.kind,
            name=self.title,
            state=self.state,
            progress=self.progress,
            doneBytes=self.doneBytes,
            totalBytes=self.totalBytes,
            canPause=self.canPause(),
            target=self.target,
            stages=tuple(stage.snapshot() for stage in self.stages),
        )

    def persistenceState(self) -> dict[str, object]:
        state = super().persistenceState()
        state.update(
            {
                "title": self.title,
                "assetName": self.assetName,
                "archiveSize": self.archiveSize,
                "executablePath": self.executablePath,
                "createdAt": self.createdAt,
                "state": self.state,
                "progress": self.progress,
                "doneBytes": self.doneBytes,
                "totalBytes": self.totalBytes,
                "target": self.target,
            }
        )
        return state

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        super().restorePersistentState(state)
        rawTitle = state.get("title")
        rawAssetName = state.get("assetName")
        rawArchiveSize = state.get("archiveSize")
        rawExecutablePath = state.get("executablePath")
        rawCreatedAt = state.get("createdAt")
        rawState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawTotalBytes = state.get("totalBytes")
        rawTarget = state.get("target")

        if isinstance(rawTitle, str) and rawTitle.strip():
            self.title = rawTitle
        if isinstance(rawAssetName, str) and rawAssetName.strip():
            self.assetName = rawAssetName
        if isinstance(rawArchiveSize, int) and not isinstance(rawArchiveSize, bool):
            self.archiveSize = max(0, rawArchiveSize)
        if isinstance(rawExecutablePath, str):
            self.executablePath = rawExecutablePath
        if isinstance(rawCreatedAt, int) and not isinstance(rawCreatedAt, bool):
            self.createdAt = rawCreatedAt
        if isinstance(rawState, str):
            self.state = _normalizeState(rawState)
        if isinstance(rawProgress, (int, float)) and not isinstance(rawProgress, bool):
            self.progress = max(0.0, min(float(rawProgress), 100.0))
        if isinstance(rawDoneBytes, int) and not isinstance(rawDoneBytes, bool):
            self.doneBytes = max(0, rawDoneBytes)
        if isinstance(rawTotalBytes, int) and not isinstance(rawTotalBytes, bool):
            self.totalBytes = max(self.archiveSize, rawTotalBytes)
        if isinstance(rawTarget, str) and rawTarget.strip():
            self.target = rawTarget
        self.syncOutput()
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
    ) -> M3U8InstallTask:
        _ = packId
        _ = kind
        _ = version
        rawTitle = state.get("title")
        rawAssetName = state.get("assetName")
        rawArchiveSize = state.get("archiveSize")
        rawExecutablePath = state.get("executablePath")
        rawCreatedAt = state.get("createdAt")
        rawTaskState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawTotalBytes = state.get("totalBytes")
        rawTarget = state.get("target")

        return cls(
            id=id,
            config=config,
            title=rawTitle if isinstance(rawTitle, str) else "N_m3u8DL-RE 安装",
            assetName=rawAssetName if isinstance(rawAssetName, str) else config.name,
            archiveSize=rawArchiveSize if isinstance(rawArchiveSize, int) else 0,
            stages=stages,
            executablePath=rawExecutablePath if isinstance(rawExecutablePath, str) else "",
            createdAt=rawCreatedAt if isinstance(rawCreatedAt, int) else None,
            state=rawTaskState if isinstance(rawTaskState, str) else "waiting",
            progress=float(rawProgress) if isinstance(rawProgress, (int, float)) else 0.0,
            doneBytes=rawDoneBytes if isinstance(rawDoneBytes, int) else 0,
            totalBytes=rawTotalBytes if isinstance(rawTotalBytes, int) else None,
            target=rawTarget if isinstance(rawTarget, str) else "",
        )

    def __hash__(self) -> int:
        return hash(self.id)


async def createInstallTask(
    *,
    installFolder: Path | str | None = None,
    proxies: Mapping[str, object] | None = None,
    chunks: int | None = None,
) -> M3U8InstallTask:
    assetInfo = await _requestReleaseAsset()
    _, archLabel = _detectRuntimeTarget()
    resolvedInstallFolder = Path(installFolder) if installFolder is not None else Path(m3u8Config.installFolder.value)
    config = TaskConfig(
        source=str(assetInfo["url"]),
        folder=resolvedInstallFolder,
        name=str(assetInfo["name"]),
        headers=_M3U8DL_RELEASE_HEADERS.copy(),
        proxies=_copyProxies(proxies) if proxies is not None else getProxies(),
        chunks=_normalizeInstallChunks(chunks),
    )
    return M3U8InstallTask(
        title=f"N_m3u8DL-RE 安装 ({archLabel})",
        assetName=str(assetInfo["name"]),
        archiveSize=int(assetInfo["size"]),
        config=config,
    )
