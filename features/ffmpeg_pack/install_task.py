# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportAny=false, reportImplicitOverride=false, reportInconsistentConstructor=false

from __future__ import annotations

import asyncio
import importlib
import platform
import sys
from collections.abc import Mapping
from collections.abc import Sequence
from pathlib import Path
from time import time_ns
from typing import Any
from uuid import uuid4

import niquests
from PySide6.QtCore import QStandardPaths
from app.feature_pack.api import TaskStatus

from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage
from app.supports.config import DEFAULT_HEADERS
from app.supports.config import cfg
from app.supports.utils import getProxies

_FFMPEG_PACK_ID = "ffmpeg_pack"
_FFMPEG_INSTALL_TASK_KIND = "ffmpeg_install"
_FFMPEG_INSTALL_TASK_VERSION = 1
_FFMPEG_INSTALL_DOWNLOAD_STAGE_KIND = "http_download"
_FFMPEG_INSTALL_EXTRACT_STAGE_KIND = "extract_archive"
_FFMPEG_INSTALL_STAGE_VERSION = 1
_FFMPEG_RELEASE_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
_FFMPEG_HEADERS = {
    "accept": "application/vnd.github+json",
    "user-agent": DEFAULT_HEADERS["user-agent"],
}


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
HttpTaskStage = _httpTaskModule.HttpTaskStage
HttpWorker = _httpTaskModule.HttpWorker
ExtractStage = _extractTaskModule.ExtractStage
ExtractWorker = _extractTaskModule.ExtractWorker


def _normalizePath(path: Path | str) -> str:
    return str(Path(path)).replace("\\", "/")


def _executableName(name: str) -> str:
    return f"{name}.exe" if sys.platform == "win32" else name


def _defaultInstallFolder() -> Path:
    return Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
    ) / "GhostDownloader" / "FFmpeg"


def _normalizeState(value: object) -> str:
    if isinstance(value, TaskStatus):
        return value.name.lower()
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"completed", "failed", "paused", "running", "waiting"}:
            return normalized
    return "waiting"


def _normalizeChunks(value: int | None) -> int:
    if value is None or isinstance(value, bool):
        return max(1, int(cfg.preBlockNum.value))
    return max(1, int(value))


def _copyHeaders(headers: Mapping[str, str] | None) -> dict[str, str]:
    if headers is None:
        return _FFMPEG_HEADERS.copy()
    return {str(key): str(value) for key, value in headers.items()}


def _copyProxies(proxies: Mapping[str, str] | None) -> dict[str, str] | None:
    if proxies is None:
        return None
    return {str(key): str(value) for key, value in proxies.items()}


def _legacyStatus(state: str) -> TaskStatus:
    return {
        "waiting": TaskStatus.WAITING,
        "running": TaskStatus.RUNNING,
        "paused": TaskStatus.PAUSED,
        "completed": TaskStatus.COMPLETED,
        "failed": TaskStatus.FAILED,
    }[_normalizeState(state)]


def _detectWindowsTarget() -> tuple[str, str]:
    if sys.platform != "win32":
        raise RuntimeError("一键安装 FFmpeg 仅支持 Windows 平台")

    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        return "win64", "x64"
    if machine in {"arm64", "aarch64"}:
        return "winarm64", "arm64"
    raise RuntimeError(f"不支持的 Windows 架构: {platform.machine()}")


def _selectReleaseAsset(assets: list[dict[str, Any]]) -> dict[str, Any]:
    target, _ = _detectWindowsTarget()
    candidates: list[tuple[int, dict[str, Any]]] = []
    for asset in assets:
        name = str(asset.get("name") or "")
        lowerName = name.lower()
        if target not in lowerName or not lowerName.endswith(".zip") or "shared" in lowerName:
            continue

        score = 0
        if "master-latest" in lowerName:
            score += 100
        if "-gpl" in lowerName:
            score += 10
        if "-latest-" in lowerName:
            score += 5
        candidates.append((score, asset))

    if not candidates:
        raise RuntimeError(f"未找到适用于当前平台的 FFmpeg 安装包: {target}")

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


async def _requestLatestReleaseAsset() -> dict[str, Any]:
    client = niquests.AsyncSession(headers=_FFMPEG_HEADERS, timeout=30, happy_eyeballs=True)
    client.trust_env = False

    try:
        response = await client.get(
            _FFMPEG_RELEASE_API,
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
        raise RuntimeError("GitHub Release 返回了不完整的 FFmpeg 安装包信息")

    return {
        "name": assetName,
        "url": downloadUrl,
        "size": size,
    }


class FFmpegInstallDownloadStage(HttpTaskStage):
    recordTaskPackId = _FFMPEG_PACK_ID
    recordTaskKind = _FFMPEG_INSTALL_TASK_KIND
    recordTaskVersion = _FFMPEG_INSTALL_TASK_VERSION
    recordKind = _FFMPEG_INSTALL_DOWNLOAD_STAGE_KIND
    recordVersion = _FFMPEG_INSTALL_STAGE_VERSION

    async def run(self) -> None:
        await super().run()

    def reset(self) -> None:
        super().reset()

    def snapshot(self):  # type: ignore[override]
        return super().snapshot()


class FFmpegInstallExtractStage(ExtractStage):
    recordTaskPackId = _FFMPEG_PACK_ID
    recordTaskKind = _FFMPEG_INSTALL_TASK_KIND
    recordTaskVersion = _FFMPEG_INSTALL_TASK_VERSION
    recordKind = _FFMPEG_INSTALL_EXTRACT_STAGE_KIND
    recordVersion = _FFMPEG_INSTALL_STAGE_VERSION

    def configure(self, config: TaskConfig) -> None:
        self.installFolder = str(Path(config.folder))

    async def run(self) -> None:
        await super().run()

    def reset(self) -> None:
        super().reset()

    def snapshot(self):  # type: ignore[override]
        return super().snapshot()


class FFmpegInstallTask(Task):
    recordPackId = _FFMPEG_PACK_ID
    recordKind = _FFMPEG_INSTALL_TASK_KIND
    recordVersion = _FFMPEG_INSTALL_TASK_VERSION

    def __init__(
        self,
        *,
        id: str | None = None,
        config: TaskConfig,
        title: str,
        assetName: str,
        archiveSize: int,
        stages: list[TaskStage] | None = None,
        ffmpegPath: str = "",
        ffprobePath: str = "",
        createdAt: int | None = None,
        state: str = "waiting",
        progress: float = 0.0,
        doneBytes: int = 0,
        totalBytes: int | None = None,
        target: str = "",
    ) -> None:
        self.title = str(title).strip() or "FFmpeg 安装"
        self.assetName = str(assetName).strip() or Path(config.name).name or "ffmpeg.zip"
        self.archiveSize = max(0, int(archiveSize))
        self.ffmpegPath = str(ffmpegPath).strip()
        self.ffprobePath = str(ffprobePath).strip()
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
            id=id or f"ffmpeg-install-task-{uuid4().hex}",
            packId=_FFMPEG_PACK_ID,
            kind=_FFMPEG_INSTALL_TASK_KIND,
            version=_FFMPEG_INSTALL_TASK_VERSION,
            config=normalizedConfig,
            stages=resolvedStages,
        )
        self.syncOutput()
        self._syncResolvedExecutables()

    @staticmethod
    def _normalizeConfig(config: TaskConfig, *, assetName: str) -> TaskConfig:
        return TaskConfig(
            source=str(config.source).strip(),
            folder=Path(config.folder),
            name=str(config.name).strip() or assetName,
            headers=_copyHeaders(config.headers),
            proxies=_copyProxies(config.proxies),
            chunks=_normalizeChunks(config.chunks),
        )

    def _buildStages(self, config: TaskConfig) -> list[TaskStage]:
        return [
            FFmpegInstallDownloadStage(
                id=f"ffmpeg-install-download-{uuid4().hex}",
                stageIndex=1,
                url=config.source,
                fileSize=self.archiveSize,
                headers=config.headers,
                proxies=config.proxies,
                resolvePath="",
                blockNum=config.chunks,
                supportsRange=True,
                kind=_FFMPEG_INSTALL_DOWNLOAD_STAGE_KIND,
                version=_FFMPEG_INSTALL_STAGE_VERSION,
                name="下载 FFmpeg",
            ),
            FFmpegInstallExtractStage(
                id=f"ffmpeg-install-extract-{uuid4().hex}",
                stageIndex=2,
                archivePath="",
                installFolder=str(config.folder),
                executableNames=[_executableName("ffmpeg"), _executableName("ffprobe")],
                cleanupArchive=True,
                kind=_FFMPEG_INSTALL_EXTRACT_STAGE_KIND,
                version=_FFMPEG_INSTALL_STAGE_VERSION,
                name="解压 FFmpeg",
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
        return self.ffmpegPath or self.archivePath

    def downloadStage(self) -> FFmpegInstallDownloadStage:
        stage = self.stages[0]
        if not isinstance(stage, FFmpegInstallDownloadStage):
            raise TypeError(
                f"Unexpected FFmpeg install download stage type: {type(stage).__name__}"
            )
        return stage

    def extractStage(self) -> FFmpegInstallExtractStage:
        stage = self.stages[1]
        if not isinstance(stage, FFmpegInstallExtractStage):
            raise TypeError(
                f"Unexpected FFmpeg install extract stage type: {type(stage).__name__}"
            )
        return stage

    def configure(self, config: TaskConfig) -> None:
        normalizedConfig = self._normalizeConfig(config, assetName=self.assetName)
        self.assetName = normalizedConfig.name
        super().configure(normalizedConfig)
        self.syncOutput()

    def syncOutput(self) -> None:
        self.target = _normalizePath(self.installFolder)
        downloadStage = self.downloadStage()
        extractStage = self.extractStage()

        downloadStage.resolvePath = self.archivePath
        downloadStage.fileSize = self.archiveSize
        extractStage.archivePath = self.archivePath
        extractStage.installFolder = self.target

        self._syncResolvedExecutables()

    def _syncResolvedExecutables(self) -> None:
        executables = self.extractStage().extractedExecutables
        ffmpegName = _executableName("ffmpeg")
        ffprobeName = _executableName("ffprobe")

        self.ffmpegPath = executables.get(
            ffmpegName,
            self.ffmpegPath or _normalizePath(self.installFolder / "bin" / ffmpegName),
        )
        self.ffprobePath = executables.get(
            ffprobeName,
            self.ffprobePath or _normalizePath(self.installFolder / "bin" / ffprobeName),
        )

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
        try:
            for stage in self.iterStages():
                self.currentStageIndex = self.stages.index(stage)
                stageState = _normalizeState(getattr(stage, "state", "waiting"))
                if stageState == "completed":
                    continue
                if isinstance(stage, FFmpegInstallDownloadStage):
                    self.state = "running"
                    await HttpWorker(stage).run()
                    self.syncStatusFromStages()
                    continue
                if isinstance(stage, FFmpegInstallExtractStage):
                    self.state = "running"
                    await ExtractWorker(stage).run()
                    self._syncResolvedExecutables()
                    self.syncStatusFromStages()
                    continue
                raise TypeError(f"不支持的 FFmpegInstallTaskStage: {type(stage).__name__}")
        except asyncio.CancelledError:
            self.syncStatusFromStages()
            raise
        except Exception:
            self.syncStatusFromStages()
            raise
        finally:
            self._syncResolvedExecutables()
            self.syncStatusFromStages()

    def reset(self) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.currentStageIndex = 0
        self.totalBytes = max(self.totalBytes, self.archiveSize)
        for stage in self.stages:
            stage.reset()
        self._syncResolvedExecutables()
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
                "ffmpegPath": self.ffmpegPath,
                "ffprobePath": self.ffprobePath,
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
        rawFfmpegPath = state.get("ffmpegPath")
        rawFfprobePath = state.get("ffprobePath")
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
        if isinstance(rawFfmpegPath, str):
            self.ffmpegPath = rawFfmpegPath
        if isinstance(rawFfprobePath, str):
            self.ffprobePath = rawFfprobePath
        if isinstance(rawCreatedAt, int) and not isinstance(rawCreatedAt, bool):
            self.createdAt = rawCreatedAt
        if isinstance(rawState, str):
            self.state = _normalizeState(rawState)
        if isinstance(rawProgress, int | float):
            self.progress = max(0.0, min(float(rawProgress), 100.0))
        if isinstance(rawDoneBytes, int) and not isinstance(rawDoneBytes, bool):
            self.doneBytes = max(0, rawDoneBytes)
        if isinstance(rawTotalBytes, int) and not isinstance(rawTotalBytes, bool):
            self.totalBytes = max(self.archiveSize, rawTotalBytes)
        if isinstance(rawTarget, str) and rawTarget.strip():
            self.target = rawTarget
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
    ) -> FFmpegInstallTask:
        _ = packId
        _ = kind
        _ = version
        rawTitle = state.get("title")
        rawAssetName = state.get("assetName")
        rawArchiveSize = state.get("archiveSize")
        rawFfmpegPath = state.get("ffmpegPath")
        rawFfprobePath = state.get("ffprobePath")
        rawCreatedAt = state.get("createdAt")
        rawTaskState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawTotalBytes = state.get("totalBytes")
        rawTarget = state.get("target")

        return cls(
            id=id,
            config=config,
            title=rawTitle if isinstance(rawTitle, str) else "FFmpeg 安装",
            assetName=rawAssetName if isinstance(rawAssetName, str) else config.name,
            archiveSize=rawArchiveSize if isinstance(rawArchiveSize, int) else 0,
            stages=stages,
            ffmpegPath=rawFfmpegPath if isinstance(rawFfmpegPath, str) else "",
            ffprobePath=rawFfprobePath if isinstance(rawFfprobePath, str) else "",
            createdAt=rawCreatedAt if isinstance(rawCreatedAt, int) else None,
            state=rawTaskState if isinstance(rawTaskState, str) else "waiting",
            progress=float(rawProgress) if isinstance(rawProgress, int | float) else 0.0,
            doneBytes=rawDoneBytes if isinstance(rawDoneBytes, int) else 0,
            totalBytes=rawTotalBytes if isinstance(rawTotalBytes, int) else None,
            target=rawTarget if isinstance(rawTarget, str) else "",
        )

    def __hash__(self) -> int:
        return hash(self.id)


async def createWindowsInstallTask(
    *,
    installFolder: Path | str | None = None,
    proxies: Mapping[str, str] | None = None,
    chunks: int | None = None,
) -> FFmpegInstallTask:
    assetInfo = await _requestLatestReleaseAsset()
    _, archLabel = _detectWindowsTarget()
    resolvedInstallFolder = Path(installFolder) if installFolder is not None else _defaultInstallFolder()
    config = TaskConfig(
        source=str(assetInfo["url"]),
        folder=resolvedInstallFolder,
        name=str(assetInfo["name"]),
        headers=_FFMPEG_HEADERS.copy(),
        proxies=_copyProxies(proxies) if proxies is not None else getProxies(),
        chunks=_normalizeChunks(chunks),
    )
    task = FFmpegInstallTask(
        title=f"FFmpeg 安装 ({archLabel})",
        assetName=str(assetInfo["name"]),
        archiveSize=int(assetInfo["size"]),
        config=config,
    )
    setattr(task, "_featurePackName", _FFMPEG_PACK_ID)
    return task


__all__ = [
    "FFmpegInstallDownloadStage",
    "FFmpegInstallExtractStage",
    "FFmpegInstallTask",
    "createWindowsInstallTask",
]
