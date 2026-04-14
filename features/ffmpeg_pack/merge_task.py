# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportAny=false, reportImplicitOverride=false, reportInconsistentConstructor=false

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from time import time_ns
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from loguru import logger

from app.bases.models import TaskStatus as LegacyTaskStatus
from app.feature_pack.api import FormField
from app.feature_pack.api import SingleFileTask
from app.feature_pack.api import StageSnapshot
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskForm
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage
from app.supports.config import cfg
from app.supports.utils import getProxies
from app.supports.utils import sanitizeFilename

from .config import resolveFFmpegExecutables

_FFMPEG_PACK_ID = "ffmpeg_pack"
_FFMPEG_MERGE_SOURCE = "gd3+ffmpeg://merge"
_FFMPEG_MERGE_TASK_KIND = "ffmpeg_merge"
_FFMPEG_MERGE_TASK_VERSION = 1
_FFMPEG_MERGE_DOWNLOAD_STAGE_KIND = "http_download"
_FFMPEG_MERGE_STAGE_KIND = "ffmpeg_merge"
_FFMPEG_MERGE_STAGE_VERSION = 1


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
HttpTaskStage = _httpTaskModule.HttpTaskStage
HttpWorker = _httpTaskModule.HttpWorker


def _normalizePath(path: Path | str) -> str:
    return str(Path(path)).replace("\\", "/")


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


def _normalizeChunks(value: int | None) -> int:
    if value is None or isinstance(value, bool):
        return max(1, int(cfg.preBlockNum.value))
    return max(1, int(value))


def _normalizeSize(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, int(value))


def _copyHeaders(headers: Mapping[str, object] | None) -> dict[str, str]:
    if not isinstance(headers, Mapping):
        return {}
    copied: dict[str, str] = {}
    for key, item in headers.items():
        if isinstance(key, str) and isinstance(item, str):
            copied[key] = item
    return copied


def _copyProxies(proxies: Mapping[str, object] | None) -> dict[str, str] | None:
    if proxies is None:
        return None
    copied: dict[str, str] = {}
    for key, item in proxies.items():
        if isinstance(key, str) and isinstance(item, str):
            copied[key] = item
    return copied


def _resourceExtension(name: str, url: str) -> str:
    fileName = Path(name).name if name else Path(urlparse(url).path).name
    return Path(fileName).suffix.lstrip(".").lower()


def _mergeOutputTitle(title: str) -> str:
    baseTitle = sanitizeFilename(title, fallback="merged-media")
    if baseTitle.lower().endswith(".mp4"):
        return baseTitle
    return f"{baseTitle}.mp4"


def _notifyAttachedTask(task: object | None) -> None:
    if task is None:
        return

    syncStatus = getattr(task, "syncStatusFromStages", None)
    if callable(syncStatus):
        syncStatus()


def _normalizeMergePayload(
    payload: Mapping[str, object],
    *,
    title: str = "",
) -> tuple[TaskConfig, dict[str, object], dict[str, object]]:
    ffmpeg, ffprobe = resolveFFmpegExecutables()
    if not ffmpeg or not ffprobe:
        raise RuntimeError("未找到可用的 ffmpeg 和 ffprobe，请先在设置中安装或配置 FFmpeg")

    rawResources = payload.get("resources")
    if not isinstance(rawResources, list) or len(rawResources) != 2:
        raise RuntimeError("在线合并暂时只支持 2 个 HTTP 音视频资源")

    normalizedResources: list[dict[str, object]] = []
    for rawResource in rawResources:
        if not isinstance(rawResource, Mapping):
            raise RuntimeError("在线合并资源格式无效")

        url = str(rawResource.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            raise RuntimeError("在线合并暂不支持 blob 或非 HTTP 资源")
        rawHeaders = rawResource.get("headers")

        normalizedResources.append(
            {
                "url": url,
                "headers": _copyHeaders(rawHeaders if isinstance(rawHeaders, Mapping) else None),
                "filename": str(rawResource.get("filename") or "").strip(),
                "size": _normalizeSize(rawResource.get("size")),
                "supportsRange": bool(rawResource.get("supportsRange")),
                "pageTitle": str(rawResource.get("pageTitle") or "").strip(),
            }
        )

    rawFolder = payload.get("path")
    folder = Path(rawFolder) if isinstance(rawFolder, (str, Path)) else Path(cfg.downloadFolder.value)
    rawProxies = payload.get("proxies")
    if isinstance(rawProxies, Mapping):
        proxies = _copyProxies(rawProxies)
    elif "proxies" in payload and rawProxies is None:
        proxies = None
    else:
        proxies = getProxies()

    rawChunks = payload.get("preBlockNum")
    chunks = _normalizeChunks(rawChunks if isinstance(rawChunks, int) else None)
    source = str(payload.get("url") or "").strip() or _FFMPEG_MERGE_SOURCE
    outputName = _mergeOutputTitle(
        title
        or str(payload.get("outputTitle") or "").strip()
        or str(payload.get("filename") or "").strip()
        or str(normalizedResources[0].get("pageTitle") or "").strip()
        or "merged-media"
    )

    config = TaskConfig(
        source=source,
        folder=folder,
        name=outputName,
        headers={},
        proxies=proxies,
        chunks=chunks,
    )
    return config, normalizedResources[0], normalizedResources[1]


class FFmpegMergeDownloadStage(HttpTaskStage):
    recordTaskPackId = _FFMPEG_PACK_ID
    recordTaskKind = _FFMPEG_MERGE_TASK_KIND
    recordTaskVersion = _FFMPEG_MERGE_TASK_VERSION
    recordKind = _FFMPEG_MERGE_DOWNLOAD_STAGE_KIND
    recordVersion = _FFMPEG_MERGE_STAGE_VERSION

    async def run(self) -> None:
        await super().run()

    def reset(self) -> None:
        super().reset()

    def snapshot(self):  # type: ignore[override]
        return super().snapshot()

    def configure(self, config: TaskConfig) -> None:
        self.proxies = _copyProxies(config.proxies)
        self.blockNum = _normalizeChunks(config.chunks)


class FFmpegStage(TaskStage):
    recordTaskPackId = _FFMPEG_PACK_ID
    recordTaskKind = _FFMPEG_MERGE_TASK_KIND
    recordTaskVersion = _FFMPEG_MERGE_TASK_VERSION
    recordKind = _FFMPEG_MERGE_STAGE_KIND
    recordVersion = _FFMPEG_MERGE_STAGE_VERSION

    def __init__(
        self,
        *,
        id: str | None = None,
        stageIndex: int = 3,
        videoPath: str,
        audioPath: str,
        resolvePath: str,
        cleanupSource: bool = True,
        kind: str = _FFMPEG_MERGE_STAGE_KIND,
        version: int = _FFMPEG_MERGE_STAGE_VERSION,
        name: str = "合并音视频",
        state: str | LegacyTaskStatus = "waiting",
        progress: float = 0.0,
        doneBytes: int = 0,
        speed: int = 0,
        error: str = "",
    ) -> None:
        super().__init__(
            id=id or f"ffmpeg-merge-stage-{uuid4().hex}",
            kind=kind,
            version=version,
            name=name,
        )
        self.stageIndex = stageIndex
        self.videoPath = str(videoPath)
        self.audioPath = str(audioPath)
        self.resolvePath = str(resolvePath)
        self.cleanupSource = bool(cleanupSource)
        self.state = _normalizeState(state)
        self.progress = max(0.0, min(float(progress), 100.0))
        self.doneBytes = max(0, int(doneBytes))
        self.speed = max(0, int(speed))
        self.error = str(error)

    @property
    def stageId(self) -> str:
        return self.id

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

    def bindTask(self, task: object) -> None:
        self.attach(task)

    def configure(self, _config: TaskConfig) -> None:
        return None

    async def run(self) -> None:
        await FFmpegWorker(self).run()

    def reset(self, notifyTask: bool = True) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.speed = 0
        self.error = ""
        if notifyTask:
            _notifyAttachedTask(getattr(self, "_task", None))
        self.stateChanged.emit(self.state)
        self.progressChanged.emit(self.progress)
        self.snapshotChanged.emit(self.snapshot())

    def setStatus(
        self,
        status: LegacyTaskStatus | str,
        *,
        emitSignals: bool = True,
        notifyTask: bool = True,
    ) -> None:
        normalizedStatus = _normalizeState(status)
        progressChanged = False
        stateChanged = self.state != normalizedStatus

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
            _notifyAttachedTask(getattr(self, "_task", None))

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
            _notifyAttachedTask(getattr(self, "_task", None))
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
            _notifyAttachedTask(getattr(self, "_task", None))
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
            "videoPath": self.videoPath,
            "audioPath": self.audioPath,
            "resolvePath": self.resolvePath,
            "cleanupSource": self.cleanupSource,
            "state": self.state,
            "progress": self.progress,
            "doneBytes": self.doneBytes,
            "speed": self.speed,
            "error": self.error,
        }

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        rawStageIndex = state.get("stageIndex")
        rawVideoPath = state.get("videoPath")
        rawAudioPath = state.get("audioPath")
        rawResolvePath = state.get("resolvePath")
        rawCleanupSource = state.get("cleanupSource")
        rawState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawSpeed = state.get("speed")
        rawError = state.get("error")

        if isinstance(rawStageIndex, int) and not isinstance(rawStageIndex, bool):
            self.stageIndex = rawStageIndex
        if isinstance(rawVideoPath, str):
            self.videoPath = rawVideoPath
        if isinstance(rawAudioPath, str):
            self.audioPath = rawAudioPath
        if isinstance(rawResolvePath, str):
            self.resolvePath = rawResolvePath
        if isinstance(rawCleanupSource, bool):
            self.cleanupSource = rawCleanupSource
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
    ) -> FFmpegStage:
        rawStageIndex = state.get("stageIndex")
        rawVideoPath = state.get("videoPath")
        rawAudioPath = state.get("audioPath")
        rawResolvePath = state.get("resolvePath")
        rawCleanupSource = state.get("cleanupSource")
        rawState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawSpeed = state.get("speed")
        rawError = state.get("error")

        return cls(
            id=id,
            stageIndex=rawStageIndex if isinstance(rawStageIndex, int) else 3,
            videoPath=rawVideoPath if isinstance(rawVideoPath, str) else "",
            audioPath=rawAudioPath if isinstance(rawAudioPath, str) else "",
            resolvePath=rawResolvePath if isinstance(rawResolvePath, str) else "",
            cleanupSource=bool(rawCleanupSource) if isinstance(rawCleanupSource, bool) else True,
            kind=kind,
            version=version,
            name=name,
            state=rawState if isinstance(rawState, str) else "waiting",
            progress=float(rawProgress) if isinstance(rawProgress, int | float) else 0.0,
            doneBytes=rawDoneBytes if isinstance(rawDoneBytes, int) else 0,
            speed=rawSpeed if isinstance(rawSpeed, int) else 0,
            error=rawError if isinstance(rawError, str) else "",
        )


class FFmpegWorker:
    def __init__(self, stage: FFmpegStage):
        self.stage = stage

    @staticmethod
    def _parseDuration(value: Any) -> float:
        try:
            duration = float(value)
        except (TypeError, ValueError):
            return 0.0

        if duration > 0:
            return duration
        return 0.0

    async def _probeDuration(self, ffprobe: str, path: str) -> float:
        process = await asyncio.create_subprocess_exec(
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="ignore").strip()
            logger.warning("ffprobe 获取时长失败: {}, {}", path, message or process.returncode)
            return 0.0

        return self._parseDuration(stdout.decode("utf-8", errors="ignore").strip())

    def _currentOutputSize(self) -> int:
        outputPath = Path(self.stage.resolvePath)
        if not outputPath.is_file():
            return self.stage.doneBytes
        return max(self.stage.doneBytes, outputPath.stat().st_size)

    async def _readProgress(
        self,
        stream: asyncio.StreamReader | None,
        totalDuration: float,
    ) -> None:
        if stream is None:
            return

        while True:
            rawLine = await stream.readline()
            if not rawLine:
                break

            line = rawLine.decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            if line.startswith("out_time_us=") and totalDuration > 0:
                currentDuration = self._parseDuration(line.removeprefix("out_time_us=")) / 1_000_000
                if currentDuration <= 0:
                    continue
                self.stage.updateTransfer(
                    doneBytes=self._currentOutputSize(),
                    speed=0,
                    progress=min(99.5, max(0.0, currentDuration / totalDuration * 100)),
                )
            elif line == "progress=end":
                self.stage.updateTransfer(
                    doneBytes=self._currentOutputSize(),
                    speed=0,
                    progress=100.0,
                )

    def _cleanupSourceFiles(self) -> None:
        for rawPath in (self.stage.videoPath, self.stage.audioPath):
            target = Path(rawPath)
            for path in (target, Path(rawPath + ".ghd")):
                try:
                    if path.is_file() or path.is_symlink():
                        path.unlink()
                except FileNotFoundError:
                    continue
                except Exception as error:
                    logger.opt(exception=error).error("failed to cleanup temporary file {}", path)

    async def run(self) -> None:
        ffmpeg, ffprobe = resolveFFmpegExecutables()
        if not ffmpeg or not ffprobe:
            self.stage.setStatus("failed")
            raise RuntimeError("未找到可用的 ffmpeg 和 ffprobe，请先在设置中安装或配置 FFmpeg")

        outputPath = Path(self.stage.resolvePath)
        outputPath.parent.mkdir(parents=True, exist_ok=True)

        process = None
        progressTask = None
        stderrOutput = ""
        try:
            self.stage.progress = 0.0
            self.stage.speed = 0
            self.stage.doneBytes = 0
            self.stage.error = ""
            self.stage.setStatus("running")
            totalDuration = await self._probeDuration(ffprobe, self.stage.videoPath)
            process = await asyncio.create_subprocess_exec(
                ffmpeg,
                "-y",
                "-v",
                "error",
                "-nostats",
                "-progress",
                "pipe:1",
                "-i",
                self.stage.videoPath,
                "-i",
                self.stage.audioPath,
                "-c",
                "copy",
                self.stage.resolvePath,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            progressTask = asyncio.create_task(self._readProgress(process.stdout, totalDuration))

            await process.wait()
            if progressTask is not None:
                await progressTask
            if process.stderr is not None:
                stderrOutput = (await process.stderr.read()).decode("utf-8", errors="ignore").strip()
            if process.returncode != 0:
                if stderrOutput:
                    raise RuntimeError(f"ffmpeg 退出码异常: {process.returncode}, {stderrOutput}")
                raise RuntimeError(f"ffmpeg 退出码异常: {process.returncode}")

            self.stage.updateTransfer(
                doneBytes=self._currentOutputSize(),
                speed=0,
                progress=100.0,
            )
            self.stage.setStatus("completed")
            if self.stage.cleanupSource:
                self._cleanupSourceFiles()
        except asyncio.CancelledError:
            self.stage.setStatus("paused")
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()
            if progressTask is not None and not progressTask.done():
                progressTask.cancel()
                with suppress(asyncio.CancelledError):
                    await progressTask
            raise
        except Exception as error:
            self.stage.setError(error)
            raise


class FFmpegMergeTask(SingleFileTask):
    recordPackId = _FFMPEG_PACK_ID
    recordKind = _FFMPEG_MERGE_TASK_KIND
    recordVersion = _FFMPEG_MERGE_TASK_VERSION

    def __init__(
        self,
        *,
        id: str | None = None,
        config: TaskConfig,
        stages: list[TaskStage],
        videoFileName: str,
        audioFileName: str,
        createdAt: int | None = None,
        state: str = "waiting",
        progress: float = 0.0,
        doneBytes: int = 0,
        totalBytes: int = 0,
        target: str = "",
    ) -> None:
        self.videoFileName = str(videoFileName).strip()
        self.audioFileName = str(audioFileName).strip()
        self.createdAt = int(time_ns()) if createdAt is None else int(createdAt)
        self.state = _normalizeState(state)
        self.progress = max(0.0, min(float(progress), 100.0))
        self.doneBytes = max(0, int(doneBytes))
        self.totalBytes = max(0, int(totalBytes))
        self.target = str(target).strip()
        normalizedConfig = self._normalizeConfig(
            config,
            fallbackName=config.name or "merged-media.mp4",
        )

        super().__init__(
            id=id or f"ffmpeg-merge-task-{uuid4().hex}",
            packId=_FFMPEG_PACK_ID,
            kind=_FFMPEG_MERGE_TASK_KIND,
            version=_FFMPEG_MERGE_TASK_VERSION,
            config=normalizedConfig,
            stages=stages,
        )
        self.url = normalizedConfig.source
        self.syncOutput()
        self.syncStatusFromStages()

    @staticmethod
    def _normalizeConfig(
        config: TaskConfig,
        *,
        fallbackName: str,
    ) -> TaskConfig:
        source = str(config.source).strip() or _FFMPEG_MERGE_SOURCE
        name = _mergeOutputTitle(str(config.name).strip() or fallbackName)
        return TaskConfig(
            source=source,
            folder=Path(config.folder),
            name=name,
            headers=_copyHeaders(config.headers),
            proxies=_copyProxies(config.proxies),
            chunks=_normalizeChunks(config.chunks),
        )

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
        self.totalBytes = max(0, int(value))

    @property
    def proxies(self) -> dict[str, str] | None:
        return _copyProxies(self.config.proxies)

    @property
    def blockNum(self) -> int:
        return self.config.chunks

    @property
    def resolvePath(self) -> str:
        return _normalizePath(self.path)

    @property
    def lastError(self) -> str:
        for stage in reversed(self.stages):
            error = getattr(stage, "error", "")
            if isinstance(error, str) and error:
                return error
        return ""

    def _downloadStage(self, stageIndex: int) -> FFmpegMergeDownloadStage:
        for stage in self.stages:
            if (
                isinstance(stage, FFmpegMergeDownloadStage)
                and getattr(stage, "stageIndex", 0) == stageIndex
            ):
                return stage
        raise TypeError(f"Unexpected FFmpeg merge download stage: {stageIndex}")

    def videoStage(self) -> FFmpegMergeDownloadStage:
        return self._downloadStage(1)

    def audioStage(self) -> FFmpegMergeDownloadStage:
        return self._downloadStage(2)

    def mergeStage(self) -> FFmpegStage:
        for stage in self.stages:
            if isinstance(stage, FFmpegStage):
                return stage
        raise TypeError("Unexpected FFmpeg merge stage")

    def setTitle(self, title: str) -> None:
        self.rename(_mergeOutputTitle(title))

    def syncStagePaths(self) -> None:
        self.syncOutput()

    def syncOutput(self) -> None:
        self.target = _normalizePath(self.path)
        videoStage = self.videoStage()
        audioStage = self.audioStage()
        mergeStage = self.mergeStage()

        videoExt = _resourceExtension(self.videoFileName, getattr(videoStage, "url", ""))
        audioExt = _resourceExtension(self.audioFileName, getattr(audioStage, "url", ""))
        finalPath = self.path
        videoPath = finalPath.with_name(
            f"{finalPath.stem}.video{f'.{videoExt}' if videoExt else ''}"
        )
        audioPath = finalPath.with_name(
            f"{finalPath.stem}.audio{f'.{audioExt}' if audioExt else ''}"
        )

        videoStage.resolvePath = _normalizePath(videoPath)
        videoStage.proxies = _copyProxies(self.config.proxies)
        videoStage.blockNum = _normalizeChunks(self.config.chunks)
        audioStage.resolvePath = _normalizePath(audioPath)
        audioStage.proxies = _copyProxies(self.config.proxies)
        audioStage.blockNum = _normalizeChunks(self.config.chunks)
        mergeStage.videoPath = _normalizePath(videoPath)
        mergeStage.audioPath = _normalizePath(audioPath)
        mergeStage.resolvePath = self.target

    def applyPayloadToTask(self, payload: Mapping[str, object]) -> None:
        updates: dict[str, object] = {}

        rawFolder = payload.get("path")
        if isinstance(rawFolder, (str, Path)):
            updates["folder"] = Path(rawFolder)

        rawName = payload.get("outputTitle")
        if not isinstance(rawName, str) or not rawName.strip():
            rawName = payload.get("filename")
        if isinstance(rawName, str) and rawName.strip():
            updates["name"] = _mergeOutputTitle(rawName)

        rawProxies = payload.get("proxies")
        if isinstance(rawProxies, Mapping):
            updates["proxies"] = _copyProxies(rawProxies)

        rawChunks = payload.get("preBlockNum")
        if isinstance(rawChunks, int) and rawChunks > 0:
            updates["chunks"] = _normalizeChunks(rawChunks)

        if not updates:
            return

        self.configure(replace(self.config, **updates))

    def setStatus(self, status: LegacyTaskStatus | str) -> LegacyTaskStatus:
        normalizedStatus = _normalizeState(status)
        if not self.stages:
            self.state = normalizedStatus
            return self.status

        for stage in self.stages:
            currentSetter = getattr(stage, "setStatus", None)
            if callable(currentSetter):
                currentSetter(normalizedStatus, emitSignals=False, notifyTask=False)

        return self.syncStatusFromStages()

    def configure(self, config: TaskConfig) -> None:
        normalizedConfig = self._normalizeConfig(config, fallbackName=self.filename)
        self.url = normalizedConfig.source
        super().configure(normalizedConfig)
        self.syncOutput()

    def editForm(self, _mode: str) -> TaskForm | None:
        return TaskForm(
            title="编辑 FFmpeg 合并任务",
            fields=(
                FormField(
                    key="name",
                    label="输出文件名",
                    kind="text",
                    placeholder="输入合并后的输出文件名",
                ),
                FormField(
                    key="folder",
                    label="输出目录",
                    kind="folder",
                    placeholder="选择输出目录",
                ),
                FormField(
                    key="proxies",
                    label="代理",
                    kind="proxy",
                    note="仅影响前置音视频下载阶段",
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
        stageSnapshots = tuple(stage.snapshot() for stage in self.stages)
        if not stageSnapshots:
            return self.status

        stageStates = [snapshot.state for snapshot in stageSnapshots]
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

        self.progress = sum(snapshot.progress for snapshot in stageSnapshots) / len(stageSnapshots)
        self.doneBytes = min(
            self.totalBytes,
            sum(max(0, int(snapshot.doneBytes)) for snapshot in stageSnapshots),
        )
        return self.status

    async def run(self) -> None:
        try:
            sortedStages = sorted(
                self.iterStages(),
                key=lambda stage: int(getattr(stage, "stageIndex", 0)),
            )
            for taskStageIndex, stage in enumerate(sortedStages):
                self.currentStageIndex = taskStageIndex
                if _normalizeState(getattr(stage, "state", "waiting")) == "completed":
                    continue

                self.state = "running"
                if isinstance(stage, FFmpegMergeDownloadStage):
                    await HttpWorker(stage).run()
                    self.syncStatusFromStages()
                    continue
                if isinstance(stage, FFmpegStage):
                    await FFmpegWorker(stage).run()
                    self.syncStatusFromStages()
                    continue
                raise TypeError(f"不支持的 FFmpegMergeTaskStage: {type(stage).__name__}")
        except asyncio.CancelledError:
            self.syncStatusFromStages()
            raise
        except Exception:
            self.syncStatusFromStages()
            raise
        finally:
            self.syncStatusFromStages()

    def reset(self) -> None:
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.currentStageIndex = 0
        for stage in self.stages:
            reset = getattr(stage, "reset", None)
            if callable(reset):
                try:
                    reset(notifyTask=False)
                except TypeError:
                    reset()
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
            totalBytes=self.totalBytes,
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
                "videoFileName": self.videoFileName,
                "audioFileName": self.audioFileName,
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
        rawVideoFileName = state.get("videoFileName")
        rawAudioFileName = state.get("audioFileName")

        if isinstance(rawCreatedAt, int) and not isinstance(rawCreatedAt, bool):
            self.createdAt = rawCreatedAt
        if isinstance(rawState, str):
            self.state = _normalizeState(rawState)
        if isinstance(rawProgress, int | float):
            self.progress = max(0.0, min(float(rawProgress), 100.0))
        if isinstance(rawDoneBytes, int) and not isinstance(rawDoneBytes, bool):
            self.doneBytes = max(0, rawDoneBytes)
        if isinstance(rawTotalBytes, int) and not isinstance(rawTotalBytes, bool):
            self.totalBytes = max(0, rawTotalBytes)
        if isinstance(rawTarget, str) and rawTarget.strip():
            self.target = rawTarget
        if isinstance(rawVideoFileName, str):
            self.videoFileName = rawVideoFileName
        if isinstance(rawAudioFileName, str):
            self.audioFileName = rawAudioFileName
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
    ) -> FFmpegMergeTask:
        _ = packId
        _ = kind
        _ = version
        rawCreatedAt = state.get("createdAt")
        rawState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawTotalBytes = state.get("totalBytes")
        rawTarget = state.get("target")
        rawVideoFileName = state.get("videoFileName")
        rawAudioFileName = state.get("audioFileName")

        return cls(
            id=id,
            config=config,
            stages=stages,
            videoFileName=rawVideoFileName if isinstance(rawVideoFileName, str) else "",
            audioFileName=rawAudioFileName if isinstance(rawAudioFileName, str) else "",
            createdAt=rawCreatedAt if isinstance(rawCreatedAt, int) else None,
            state=rawState if isinstance(rawState, str) else "waiting",
            progress=float(rawProgress) if isinstance(rawProgress, int | float) else 0.0,
            doneBytes=rawDoneBytes if isinstance(rawDoneBytes, int) else 0,
            totalBytes=rawTotalBytes if isinstance(rawTotalBytes, int) else 0,
            target=rawTarget if isinstance(rawTarget, str) else "",
        )

    def __hash__(self) -> int:
        return hash(self.id)

    def occupiesDownloadSlot(self) -> bool:
        return self.state == "running"

    def willOccupyDownloadSlotWhenStarted(self) -> bool:
        return True


async def createBrowserMergeTask(
    payload: Mapping[str, object],
    title: str = "",
) -> FFmpegMergeTask:
    config, videoResource, audioResource = _normalizeMergePayload(payload, title=title)
    videoSize = _normalizeSize(videoResource.get("size"))
    audioSize = _normalizeSize(audioResource.get("size"))
    videoHeaders = videoResource.get("headers")
    audioHeaders = audioResource.get("headers")
    task = FFmpegMergeTask(
        config=config,
        stages=[
            FFmpegMergeDownloadStage(
                id=f"ffmpeg-merge-download-video-{uuid4().hex}",
                stageIndex=1,
                url=str(videoResource["url"]),
                fileSize=videoSize,
                headers=_copyHeaders(videoHeaders if isinstance(videoHeaders, Mapping) else None),
                proxies=_copyProxies(config.proxies),
                resolvePath="",
                blockNum=config.chunks,
                supportsRange=bool(videoResource.get("supportsRange")),
                kind=_FFMPEG_MERGE_DOWNLOAD_STAGE_KIND,
                version=_FFMPEG_MERGE_STAGE_VERSION,
                name="下载视频",
            ),
            FFmpegMergeDownloadStage(
                id=f"ffmpeg-merge-download-audio-{uuid4().hex}",
                stageIndex=2,
                url=str(audioResource["url"]),
                fileSize=audioSize,
                headers=_copyHeaders(audioHeaders if isinstance(audioHeaders, Mapping) else None),
                proxies=_copyProxies(config.proxies),
                resolvePath="",
                blockNum=config.chunks,
                supportsRange=bool(audioResource.get("supportsRange")),
                kind=_FFMPEG_MERGE_DOWNLOAD_STAGE_KIND,
                version=_FFMPEG_MERGE_STAGE_VERSION,
                name="下载音频",
            ),
            FFmpegStage(
                id=f"ffmpeg-merge-stage-{uuid4().hex}",
                stageIndex=3,
                videoPath="",
                audioPath="",
                resolvePath="",
                cleanupSource=True,
                kind=_FFMPEG_MERGE_STAGE_KIND,
                version=_FFMPEG_MERGE_STAGE_VERSION,
                name="合并音视频",
            ),
        ],
        videoFileName=str(videoResource.get("filename") or ""),
        audioFileName=str(audioResource.get("filename") or ""),
        totalBytes=videoSize + audioSize,
    )
    setattr(task, "_featurePackName", _FFMPEG_PACK_ID)
    return task


__all__ = [
    "FFmpegMergeDownloadStage",
    "FFmpegMergeTask",
    "FFmpegStage",
    "FFmpegWorker",
    "createBrowserMergeTask",
]
