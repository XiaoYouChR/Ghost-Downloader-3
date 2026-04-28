# pyright: reportAny=false, reportExplicitAny=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportAttributeAccessIssue=false, reportImplicitOverride=false, reportInconsistentConstructor=false, reportUntypedBaseClass=false, reportUnannotatedClassAttribute=false, reportUnusedCallResult=false, reportUnusedParameter=false, reportArgumentType=false, reportPropertyTypeMismatch=false, reportUnknownLambdaType=false, reportUnusedImport=false

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from time import time_ns
from typing import Any
from typing import cast
from uuid import uuid4

from loguru import logger

from app.bases.models import TaskStatus as LegacyTaskStatus
from app.feature_pack.api import FormField
from app.feature_pack.api import MultiFileTask
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskFile
from app.feature_pack.api import TaskForm
from app.feature_pack.api import TaskSnapshot
from app.feature_pack.api import TaskStage
from app.supports.config import DEFAULT_HEADERS
from app.supports.config import cfg
from app.supports.utils import getProxies
from app.supports.utils import sanitizeFilename


_BILIBILI_PACK_ID = "bili_pack"
_BILIBILI_TASK_KIND = "bilibili_download"
_BILIBILI_TASK_VERSION = 1
_HTTP_STAGE_KIND = "http_download"
_FFMPEG_STAGE_KIND = "ffmpeg_merge"
_STAGE_VERSION = 1


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
_ffmpegTaskModule = _importPackModule("ffmpeg_pack", "task")
HttpTaskStage = _httpTaskModule.HttpTaskStage
HttpWorker = _httpTaskModule.HttpWorker
FFmpegStage = _ffmpegTaskModule.FFmpegStage
FFmpegWorker = _ffmpegTaskModule.FFmpegWorker


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


def _copyProxies(proxies: Mapping[str, object] | None) -> dict[str, str] | None:
    if proxies is None:
        return None
    return {str(key): str(value) for key, value in proxies.items()}


def _normalizeChunks(value: int | None) -> int:
    if value is None or isinstance(value, bool):
        return max(1, int(cfg.preBlockNum.value))
    return max(1, int(value))


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


def _pageId(pageNumber: int) -> str:
    return f"page-{max(1, int(pageNumber))}"


def _pageNumberFromId(fileId: str, fallback: int) -> int:
    prefix, _, suffix = fileId.partition("-")
    if prefix == "page" and suffix.isdecimal():
        return max(1, int(suffix))
    if fileId.isdecimal():
        return max(1, int(fileId))
    return max(1, fallback)


def _baseName(name: str, *, fallback: str = "bilibili_video") -> str:
    sanitizedName = sanitizeFilename(str(name).strip(), fallback=fallback)
    if sanitizedName.lower().endswith(".mp4"):
        return sanitizedName[:-4] or fallback
    return sanitizedName


def _normalizeConfig(
    config: TaskConfig,
    *,
    fallbackName: str = "bilibili_video",
) -> TaskConfig:
    return TaskConfig(
        source=str(config.source).strip(),
        folder=Path(config.folder),
        name=_baseName(config.name, fallback=fallbackName),
        headers=_copyHeaders(config.headers, useDefaults=True),
        proxies=_copyProxies(config.proxies),
        chunks=_normalizeChunks(config.chunks),
    )


def _notifyAttachedTask(stage: object) -> None:
    task = getattr(stage, "_task", None)
    syncStatus = getattr(task, "syncStatusFromStages", None)
    if callable(syncStatus):
        syncStatus()


@dataclass(slots=True, kw_only=True)
class BilibiliEpisodeFile(TaskFile):
    id: str = ""
    path: str = ""
    size: int = 0
    pageNumber: int = 1
    part: str = ""
    cid: int = 0
    videoUrl: str = ""
    audioUrl: str = ""
    videoSize: int = 0
    audioSize: int = 0

    def __post_init__(self) -> None:
        self.pageNumber = max(1, int(self.pageNumber))
        if not self.id:
            self.id = _pageId(self.pageNumber)
        self.path = str(self.path or f"P{self.pageNumber}.mp4")
        self.size = max(0, int(self.size or self.videoSize + self.audioSize))
        self.videoSize = max(0, int(self.videoSize))
        self.audioSize = max(0, int(self.audioSize))
        self.cid = max(0, int(self.cid))
        self.part = str(self.part)
        self.videoUrl = str(self.videoUrl)
        self.audioUrl = str(self.audioUrl)


def _coerceEpisodeFile(rawFile: object, fallbackIndex: int) -> BilibiliEpisodeFile:
    fallbackPageNumber = fallbackIndex + 1
    if isinstance(rawFile, BilibiliEpisodeFile):
        return rawFile
    if isinstance(rawFile, TaskFile):
        pageNumber = _pageNumberFromId(rawFile.id, fallbackPageNumber)
        return BilibiliEpisodeFile(
            id=rawFile.id,
            path=rawFile.path,
            size=rawFile.size,
            selected=rawFile.selected,
            note=rawFile.note,
            doneBytes=rawFile.doneBytes,
            finished=rawFile.finished,
            pageNumber=pageNumber,
        )
    if isinstance(rawFile, Mapping):
        rawId = rawFile.get("id")
        rawPath = rawFile.get("path")
        rawSize = rawFile.get("size")
        rawPageNumber = rawFile.get("pageNumber")
        pageNumber = (
            rawPageNumber
            if isinstance(rawPageNumber, int) and not isinstance(rawPageNumber, bool)
            else _pageNumberFromId(rawId, fallbackPageNumber)
            if isinstance(rawId, str)
            else fallbackPageNumber
        )
        rawVideoSize = rawFile.get("videoSize")
        rawAudioSize = rawFile.get("audioSize")
        rawCid = rawFile.get("cid")
        rawDoneBytes = rawFile.get("doneBytes", 0)
        rawPart = rawFile.get("part")
        rawVideoUrl = rawFile.get("videoUrl")
        rawAudioUrl = rawFile.get("audioUrl")
        rawNote = rawFile.get("note")
        return BilibiliEpisodeFile(
            id=rawId if isinstance(rawId, str) and rawId else _pageId(pageNumber),
            path=rawPath if isinstance(rawPath, str) and rawPath else f"P{pageNumber}.mp4",
            size=rawSize if isinstance(rawSize, int) and not isinstance(rawSize, bool) else 0,
            selected=bool(rawFile.get("selected", True)),
            note=rawNote if isinstance(rawNote, str) else "",
            doneBytes=rawDoneBytes if isinstance(rawDoneBytes, int) and not isinstance(rawDoneBytes, bool) else 0,
            finished=bool(rawFile.get("finished", False)),
            pageNumber=pageNumber,
            part=rawPart if isinstance(rawPart, str) else "",
            cid=rawCid if isinstance(rawCid, int) and not isinstance(rawCid, bool) else 0,
            videoUrl=rawVideoUrl if isinstance(rawVideoUrl, str) else "",
            audioUrl=rawAudioUrl if isinstance(rawAudioUrl, str) else "",
            videoSize=rawVideoSize if isinstance(rawVideoSize, int) and not isinstance(rawVideoSize, bool) else 0,
            audioSize=rawAudioSize if isinstance(rawAudioSize, int) and not isinstance(rawAudioSize, bool) else 0,
        )
    raise TypeError(f"Unsupported Bilibili episode file type: {type(rawFile).__name__}")


def _restoreEpisodeFiles(state: Mapping[str, object]) -> list[BilibiliEpisodeFile]:
    rawFiles = state.get("files")
    if not isinstance(rawFiles, list):
        return []

    metadataById: dict[str, Mapping[str, object]] = {}
    rawMetadata = state.get("episodeMetadata")
    if isinstance(rawMetadata, list):
        for rawItem in rawMetadata:
            if not isinstance(rawItem, Mapping):
                continue
            rawId = rawItem.get("id")
            if isinstance(rawId, str) and rawId:
                metadataById[rawId] = rawItem

    restoredFiles: list[BilibiliEpisodeFile] = []
    for fallbackIndex, rawFile in enumerate(rawFiles):
        if not isinstance(rawFile, Mapping):
            continue
        mergedFile = dict(rawFile)
        rawId = rawFile.get("id")
        if isinstance(rawId, str):
            mergedFile.update(metadataById.get(rawId, {}))
        restoredFiles.append(_coerceEpisodeFile(mergedFile, fallbackIndex))
    return restoredFiles


class BilibiliDownloadStage(HttpTaskStage):
    recordTaskPackId = _BILIBILI_PACK_ID
    recordTaskKind = _BILIBILI_TASK_KIND
    recordTaskVersion = _BILIBILI_TASK_VERSION
    recordKind = _HTTP_STAGE_KIND
    recordVersion = _STAGE_VERSION

    def __init__(
        self,
        *,
        id: str | None = None,
        fileId: str = "",
        pageNumber: int = 1,
        mediaKind: str = "video",
        **kwargs: Any,
    ) -> None:
        super().__init__(id=id or f"bilibili-http-stage-{uuid4().hex}", **kwargs)
        self.fileId = str(fileId)
        self.pageNumber = max(1, int(pageNumber))
        self.mediaKind = "audio" if mediaKind == "audio" else "video"

    def configure(self, config: TaskConfig) -> None:
        self.headers = _copyHeaders(config.headers, useDefaults=True)
        self.proxies = _copyProxies(config.proxies)
        self.blockNum = _normalizeChunks(config.chunks)

    async def run(self) -> None:
        await super().run()

    def reset(self, notifyTask: bool = True) -> None:
        super().reset(notifyTask=False)
        if notifyTask:
            _notifyAttachedTask(self)

    def snapshot(self):  # type: ignore[override]
        return super().snapshot()

    def setStatus(
        self,
        status: LegacyTaskStatus | str,
        *,
        emitSignals: bool = True,
        notifyTask: bool | None = None,
    ) -> None:
        super().setStatus(status, emitSignals=emitSignals, notifyTask=False)
        if notifyTask is not False:
            _notifyAttachedTask(self)

    def setError(self, error: Any, notifyTask: bool = True) -> None:
        super().setError(error, notifyTask=False)
        if notifyTask:
            _notifyAttachedTask(self)

    def updateTransfer(
        self,
        *,
        doneBytes: int,
        speed: int,
        progress: float,
        notifyTask: bool = True,
    ) -> None:
        super().updateTransfer(
            doneBytes=doneBytes,
            speed=speed,
            progress=progress,
            notifyTask=False,
        )
        if notifyTask:
            _notifyAttachedTask(self)

    def persistenceState(self) -> dict[str, object]:
        state = super().persistenceState()
        state.update(
            {
                "fileId": self.fileId,
                "pageNumber": self.pageNumber,
                "mediaKind": self.mediaKind,
            }
        )
        return state

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        super().restorePersistentState(state)
        rawFileId = state.get("fileId")
        rawPageNumber = state.get("pageNumber")
        rawMediaKind = state.get("mediaKind")
        if isinstance(rawFileId, str):
            self.fileId = rawFileId
        if isinstance(rawPageNumber, int) and not isinstance(rawPageNumber, bool):
            self.pageNumber = max(1, rawPageNumber)
        if isinstance(rawMediaKind, str) and rawMediaKind in {"audio", "video"}:
            self.mediaKind = rawMediaKind


class BilibiliMergeStage(FFmpegStage):
    recordTaskPackId = _BILIBILI_PACK_ID
    recordTaskKind = _BILIBILI_TASK_KIND
    recordTaskVersion = _BILIBILI_TASK_VERSION
    recordKind = _FFMPEG_STAGE_KIND
    recordVersion = _STAGE_VERSION

    def __init__(
        self,
        *,
        id: str | None = None,
        fileId: str = "",
        pageNumber: int = 1,
        **kwargs: Any,
    ) -> None:
        super().__init__(id=id or f"bilibili-merge-stage-{uuid4().hex}", **kwargs)
        self.fileId = str(fileId)
        self.pageNumber = max(1, int(pageNumber))

    async def run(self) -> None:
        await super().run()

    def reset(self, notifyTask: bool = True) -> None:
        super().reset(notifyTask=notifyTask)

    def snapshot(self):  # type: ignore[override]
        return super().snapshot()

    def persistenceState(self) -> dict[str, object]:
        state = super().persistenceState()
        state.update({"fileId": self.fileId, "pageNumber": self.pageNumber})
        return state

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        super().restorePersistentState(state)
        rawFileId = state.get("fileId")
        rawPageNumber = state.get("pageNumber")
        if isinstance(rawFileId, str):
            self.fileId = rawFileId
        if isinstance(rawPageNumber, int) and not isinstance(rawPageNumber, bool):
            self.pageNumber = max(1, rawPageNumber)


class BilibiliTask(MultiFileTask):
    recordPackId = _BILIBILI_PACK_ID
    recordKind = _BILIBILI_TASK_KIND
    recordVersion = _BILIBILI_TASK_VERSION

    def __init__(
        self,
        *,
        id: str | None = None,
        config: TaskConfig | None = None,
        stages: list[TaskStage] | None = None,
        files: list[TaskFile | Mapping[str, object]] | None = None,
        createdAt: int | None = None,
        title: str | None = None,
        url: str | None = None,
        fileSize: int | None = None,
        path: Path | str | None = None,
        headers: Mapping[str, object] | None = None,
        proxies: Mapping[str, object] | None = None,
        blockNum: int | None = None,
        selectedPages: list[int] | None = None,
        pageParts: list[str] | None = None,
        totalPages: int | None = None,
    ) -> None:
        _ = selectedPages
        _ = pageParts
        _ = totalPages
        if config is None:
            resolvedSource = str(url or "").strip()
            if not resolvedSource:
                raise ValueError("BilibiliTask requires TaskConfig or url")
            config = TaskConfig(
                source=resolvedSource,
                folder=Path(path) if path is not None else Path(cfg.downloadFolder.value),
                name=_baseName(str(title or "").strip(), fallback="bilibili_video"),
                headers=_copyHeaders(headers, useDefaults=True),
                proxies=_copyProxies(proxies) if proxies is not None else getProxies(),
                chunks=_normalizeChunks(blockNum),
            )

        normalizedConfig = _normalizeConfig(config)
        normalizedFiles = [
            _coerceEpisodeFile(rawFile, index)
            for index, rawFile in enumerate(files or [])
        ]

        self.createdAt = int(time_ns()) if createdAt is None else int(createdAt)
        self.url = normalizedConfig.source
        self.state = "waiting"
        self.progress = 0.0
        self.doneBytes = 0
        self.totalBytes = max(0, int(fileSize)) if fileSize is not None else 0
        self.target = ""
        self._filesById: dict[str, BilibiliEpisodeFile] = {}
        self._filesByPageNumber: dict[int, BilibiliEpisodeFile] = {}

        resolvedStages = stages or self._buildStages(
            files=normalizedFiles,
            config=normalizedConfig,
        )
        super().__init__(
            id=id or f"bilibili-task-{uuid4().hex}",
            packId=_BILIBILI_PACK_ID,
            kind=_BILIBILI_TASK_KIND,
            version=_BILIBILI_TASK_VERSION,
            config=normalizedConfig,
            stages=resolvedStages,
            files=normalizedFiles,
        )
        self._rebuildFileIndexes()
        self._normalizeStageLinks()
        self.syncOutput()
        self.syncStatusFromStages()

    @property
    def taskId(self) -> str:
        return self.id

    @property
    def title(self) -> str:
        return self.config.name

    @title.setter
    def title(self, value: str) -> None:
        self.setTitle(value)

    @property
    def path(self) -> Path:
        return self.config.folder

    @property
    def headers(self) -> dict[str, str]:
        return dict(self.config.headers)

    @property
    def proxies(self) -> dict[str, str] | None:
        return _copyProxies(self.config.proxies)

    @property
    def blockNum(self) -> int:
        return self.config.chunks

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
        self.totalBytes = max(0, int(value))

    @property
    def selectedPages(self) -> list[int]:
        return [file.pageNumber for file in self.files if file.selected]

    @property
    def pageParts(self) -> list[str]:
        return [file.part for file in self.files if file.selected]

    @property
    def totalPages(self) -> int:
        return self.fileCount

    @property
    def selectedFileCount(self) -> int:
        return self.selectedCount

    @property
    def totalFileCount(self) -> int:
        return self.fileCount

    @property
    def resolvePath(self) -> str:
        selectedFiles = [file for file in self.files if file.selected]
        if len(selectedFiles) == 1:
            return str(self.outputPathForFile(selectedFiles[0]))
        return self.target

    @property
    def lastError(self) -> str:
        for stage in reversed(self.stages):
            error = getattr(stage, "error", "")
            if isinstance(error, str) and error:
                return error
        return ""

    def _buildStages(
        self,
        *,
        files: list[BilibiliEpisodeFile],
        config: TaskConfig,
    ) -> list[TaskStage]:
        stages: list[TaskStage] = []
        for index, file in enumerate(files):
            baseStageIndex = index * 3
            stages.extend(
                [
                    BilibiliDownloadStage(
                        stageIndex=baseStageIndex + 1,
                        fileId=file.id,
                        pageNumber=file.pageNumber,
                        mediaKind="video",
                        url=file.videoUrl,
                        fileSize=file.videoSize,
                        headers=config.headers,
                        proxies=config.proxies,
                        resolvePath="",
                        blockNum=config.chunks,
                        supportsRange=True,
                        kind=_HTTP_STAGE_KIND,
                        version=_STAGE_VERSION,
                        name=f"P{file.pageNumber} 视频",
                    ),
                    BilibiliDownloadStage(
                        stageIndex=baseStageIndex + 2,
                        fileId=file.id,
                        pageNumber=file.pageNumber,
                        mediaKind="audio",
                        url=file.audioUrl,
                        fileSize=file.audioSize,
                        headers=config.headers,
                        proxies=config.proxies,
                        resolvePath="",
                        blockNum=config.chunks,
                        supportsRange=True,
                        kind=_HTTP_STAGE_KIND,
                        version=_STAGE_VERSION,
                        name=f"P{file.pageNumber} 音频",
                    ),
                    BilibiliMergeStage(
                        stageIndex=baseStageIndex + 3,
                        fileId=file.id,
                        pageNumber=file.pageNumber,
                        videoPath="",
                        audioPath="",
                        resolvePath="",
                        cleanupSource=True,
                        kind=_FFMPEG_STAGE_KIND,
                        version=_STAGE_VERSION,
                        name=f"P{file.pageNumber} 合并",
                    ),
                ]
            )
        return stages

    def _rebuildFileIndexes(self) -> None:
        episodeFiles: list[BilibiliEpisodeFile] = []
        for index, rawFile in enumerate(self.files):
            episodeFiles.append(_coerceEpisodeFile(rawFile, index))
        self.files = episodeFiles
        self._filesById = {file.id: file for file in episodeFiles}
        self._filesByPageNumber = {file.pageNumber: file for file in episodeFiles}

    def _normalizeStageLinks(self) -> None:
        sortedFiles = sorted(self.files, key=lambda file: file.pageNumber)
        for stage in self.stages:
            stageIndex = int(getattr(stage, "stageIndex", 1))
            fileIndex = max(0, (stageIndex - 1) // 3)
            fallbackFile = sortedFiles[fileIndex] if fileIndex < len(sortedFiles) else None
            fileId = getattr(stage, "fileId", "")
            file = self._filesById.get(fileId) if isinstance(fileId, str) else None
            file = file or fallbackFile
            if file is None:
                continue

            setattr(stage, "fileId", file.id)
            setattr(stage, "pageNumber", file.pageNumber)
            if isinstance(stage, BilibiliDownloadStage):
                stage.mediaKind = "audio" if stageIndex % 3 == 2 else "video"
                stage.url = file.audioUrl if stage.mediaKind == "audio" else file.videoUrl
                stage.fileSize = file.audioSize if stage.mediaKind == "audio" else file.videoSize

    def _outputFileName(self, file: BilibiliEpisodeFile) -> str:
        baseTitle = _baseName(self.config.name, fallback="bilibili_video")
        if self.fileCount <= 1:
            return f"{baseTitle}.mp4"

        suffix = f"P{file.pageNumber}"
        part = sanitizeFilename(file.part, fallback="").strip() if file.part.strip() else ""
        if part and part != baseTitle:
            return f"{baseTitle} - {suffix} {part}.mp4"
        return f"{baseTitle} - {suffix}.mp4"

    def outputPathForFile(self, file: BilibiliEpisodeFile) -> Path:
        return self.root / self._outputFileName(file)

    def syncStagePaths(self) -> None:
        self.syncOutput()

    def syncOutput(self) -> None:
        self.target = str(self.root)
        self._rebuildFileIndexes()
        self._normalizeStageLinks()

        for file in self.files:
            file.path = self._outputFileName(file)

            finalPath = self.outputPathForFile(file)
            videoPath = finalPath.with_name(f"{finalPath.stem}.video.m4s")
            audioPath = finalPath.with_name(f"{finalPath.stem}.audio.m4s")

            videoStage = self.downloadStage(file.id, "video")
            audioStage = self.downloadStage(file.id, "audio")
            mergeStage = self.mergeStage(file.id)
            if videoStage is not None:
                videoStage.resolvePath = str(videoPath)
                videoStage.headers = dict(self.config.headers)
                videoStage.proxies = _copyProxies(self.config.proxies)
                videoStage.blockNum = _normalizeChunks(self.config.chunks)
            if audioStage is not None:
                audioStage.resolvePath = str(audioPath)
                audioStage.headers = dict(self.config.headers)
                audioStage.proxies = _copyProxies(self.config.proxies)
                audioStage.blockNum = _normalizeChunks(self.config.chunks)
            if mergeStage is not None:
                mergeStage.videoPath = str(videoPath)
                mergeStage.audioPath = str(audioPath)
                mergeStage.resolvePath = str(finalPath)

    def downloadStage(
        self,
        fileId: str,
        mediaKind: str,
    ) -> BilibiliDownloadStage | None:
        for stage in self.stages:
            if (
                isinstance(stage, BilibiliDownloadStage)
                and stage.fileId == fileId
                and stage.mediaKind == mediaKind
            ):
                return stage
        return None

    def mergeStage(self, fileId: str) -> BilibiliMergeStage | None:
        for stage in self.stages:
            if isinstance(stage, BilibiliMergeStage) and stage.fileId == fileId:
                return stage
        return None

    @property
    def selectedStages(self) -> list[TaskStage]:
        selectedIds = self.selectedIds
        return [
            stage
            for stage in sorted(
                self.stages,
                key=lambda item: int(getattr(item, "stageIndex", 0)),
            )
            if str(getattr(stage, "fileId", "")) in selectedIds
        ]

    def setTitle(self, title: str) -> None:
        self.configure(replace(self.config, name=_baseName(title, fallback=self.config.name)))

    def _recalculateSelection(self) -> None:
        self.totalBytes = sum(file.size for file in self.files if file.selected)

    def _syncFileProgress(self) -> None:
        for file in self.files:
            videoStage = self.downloadStage(file.id, "video")
            audioStage = self.downloadStage(file.id, "audio")
            mergeStage = self.mergeStage(file.id)
            doneBytes = 0
            if videoStage is not None:
                doneBytes += max(0, int(videoStage.doneBytes))
            if audioStage is not None:
                doneBytes += max(0, int(audioStage.doneBytes))
            file.doneBytes = min(file.size, doneBytes) if file.size > 0 else doneBytes
            file.finished = bool(mergeStage is not None and mergeStage.state == "completed")
            if file.finished and file.size > 0:
                file.doneBytes = max(file.doneBytes, file.size)

    def select(self, ids: set[str]) -> None:
        if not ids:
            raise ValueError("至少需要选择一个分集")
        previousIds = self.selectedIds
        super().select(ids)
        if previousIds == self.selectedIds:
            return
        self._syncFileProgress()
        self.syncStatusFromStages()
        self.snapshotChanged.emit(self.snapshot())

    def updateSelectedPages(self, selectedPages: set[int]) -> None:
        self.select({_pageId(pageNumber) for pageNumber in selectedPages})

    def configure(self, config: TaskConfig) -> None:
        normalizedConfig = _normalizeConfig(config, fallbackName=self.config.name)
        self.url = normalizedConfig.source
        super().configure(normalizedConfig)
        self._syncFileProgress()
        self.syncStatusFromStages()

    def applyPayloadToTask(self, payload: dict[str, Any]) -> None:
        updates: dict[str, object] = {}

        rawFolder = payload.get("path")
        if isinstance(rawFolder, (str, Path)):
            updates["folder"] = Path(rawFolder)

        rawName = payload.get("filename")
        if isinstance(rawName, str) and rawName.strip():
            updates["name"] = _baseName(rawName, fallback=self.config.name)

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

        if updates:
            self.configure(replace(self.config, **updates))

    def editForm(self, _mode: str) -> TaskForm | None:
        return TaskForm(
            title="编辑 Bilibili 下载任务",
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
                    label="选择分集",
                    kind="files",
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

    def syncStatusFromStages(self) -> LegacyTaskStatus:
        self._syncFileProgress()
        selectedStages = self.selectedStages
        if not selectedStages:
            self.state = "waiting"
            self.progress = 0.0
            self.doneBytes = 0
            self.totalBytes = 0
            return self.status

        stageStates = [
            _normalizeState(getattr(stage, "state", "waiting"))
            for stage in selectedStages
        ]
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
        self.doneBytes = sum(file.doneBytes for file in self.files if file.selected)
        if not activeStates:
            self.progress = 100.0
            self.doneBytes = max(self.doneBytes, self.totalBytes)
        else:
            self.progress = (
                sum(float(getattr(stage, "progress", 0.0)) for stage in selectedStages)
                / len(selectedStages)
            )
        return self.status

    def setState(self, state: str) -> None:
        normalizedState = _normalizeState(state)
        self.state = normalizedState
        self.stateChanged.emit(normalizedState)
        self.snapshotChanged.emit(self.snapshot())

    def setStatus(self, status: LegacyTaskStatus | str) -> LegacyTaskStatus:
        normalizedStatus = _normalizeState(status)
        for stage in self.selectedStages:
            currentSetter = getattr(stage, "setStatus", None)
            if not callable(currentSetter):
                continue
            if _normalizeState(getattr(stage, "state", "waiting")) == "completed":
                continue
            if normalizedStatus == "running" and _normalizeState(getattr(stage, "state", "")) == "failed":
                reset = getattr(stage, "reset", None)
                if callable(reset):
                    reset(notifyTask=False)
            currentSetter(normalizedStatus, emitSignals=False, notifyTask=False)
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
            reset = getattr(stage, "reset", None)
            if not callable(reset):
                continue
            try:
                reset(notifyTask=False)
            except TypeError:
                reset()
        self.syncStatusFromStages()

    def canPause(self) -> bool:
        selectedStages = self.selectedStages
        return bool(selectedStages) and all(stage.canPause() for stage in selectedStages)

    async def run(self) -> None:
        currentStage: TaskStage | None = None
        if self.state != "running":
            self.setState("running")

        try:
            for stage in self.selectedStages:
                if self.state != "running":
                    break
                if _normalizeState(getattr(stage, "state", "waiting")) == "completed":
                    continue

                currentStage = stage
                self.currentStageIndex = self.stages.index(stage)
                if isinstance(stage, BilibiliDownloadStage):
                    await HttpWorker(stage).run()
                    self.syncStatusFromStages()
                    continue
                if isinstance(stage, BilibiliMergeStage):
                    await FFmpegWorker(stage).run()
                    self.syncStatusFromStages()
                    continue
                raise TypeError(f"不支持的 BilibiliTaskStage: {type(stage).__name__}")
        except asyncio.CancelledError:
            logger.info("{} 停止下载", self.title)
            raise
        except Exception as error:
            setError = getattr(currentStage, "setError", None)
            if currentStage is not None and callable(setError) and not getattr(currentStage, "error", ""):
                setError(error)
            logger.opt(exception=error).error("{} 下载失败", self.title)
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
                "createdAt": self.createdAt,
                "url": self.url,
                "state": self.state,
                "progress": self.progress,
                "doneBytes": self.doneBytes,
                "totalBytes": self.totalBytes,
                "episodeMetadata": [
                    {
                        "id": file.id,
                        "pageNumber": file.pageNumber,
                        "part": file.part,
                        "cid": file.cid,
                        "videoUrl": file.videoUrl,
                        "audioUrl": file.audioUrl,
                        "videoSize": file.videoSize,
                        "audioSize": file.audioSize,
                    }
                    for file in self.files
                    if isinstance(file, BilibiliEpisodeFile)
                ],
            }
        )
        return state

    def restorePersistentState(self, state: Mapping[str, object]) -> None:
        Task.restorePersistentState(self, state)
        rawCreatedAt = state.get("createdAt")
        rawUrl = state.get("url")
        rawTaskState = state.get("state")
        rawProgress = state.get("progress")
        rawDoneBytes = state.get("doneBytes")
        rawTotalBytes = state.get("totalBytes")

        if isinstance(rawCreatedAt, int) and not isinstance(rawCreatedAt, bool):
            self.createdAt = rawCreatedAt
        if isinstance(rawUrl, str) and rawUrl:
            self.url = rawUrl
        if isinstance(rawTaskState, str):
            self.state = _normalizeState(rawTaskState)
        if isinstance(rawProgress, int | float):
            self.progress = max(0.0, min(float(rawProgress), 100.0))
        if isinstance(rawDoneBytes, int) and not isinstance(rawDoneBytes, bool):
            self.doneBytes = max(0, rawDoneBytes)
        if isinstance(rawTotalBytes, int) and not isinstance(rawTotalBytes, bool):
            self.totalBytes = max(0, rawTotalBytes)

        restoredFiles = _restoreEpisodeFiles(state)
        if restoredFiles:
            self.files = restoredFiles
        self._rebuildFileIndexes()
        self._normalizeStageLinks()
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
    ) -> BilibiliTask:
        _ = packId
        _ = kind
        _ = version
        rawCreatedAt = state.get("createdAt")
        rawTotalBytes = state.get("totalBytes")
        files = _restoreEpisodeFiles(state)

        return cls(
            id=id,
            config=config,
            stages=stages,
            files=files,
            createdAt=rawCreatedAt if isinstance(rawCreatedAt, int) else None,
            fileSize=rawTotalBytes if isinstance(rawTotalBytes, int) else None,
        )

    def __hash__(self) -> int:
        return hash(self.id)

    def occupiesDownloadSlot(self) -> bool:
        return self.state == "running"

    def willOccupyDownloadSlotWhenStarted(self) -> bool:
        return True


def createBilibiliTask(
    *,
    config: TaskConfig,
    episodes: list[BilibiliEpisodeFile],
    fallbackName: str,
) -> BilibiliTask:
    normalizedConfig = _normalizeConfig(config, fallbackName=fallbackName)
    if not episodes:
        raise ValueError("Bilibili 任务缺少可下载分集")
    if not any(file.selected for file in episodes):
        raise ValueError("至少需要选择一个分集")

    task = BilibiliTask(
        config=normalizedConfig,
        files=episodes,
        fileSize=sum(file.size for file in episodes if file.selected),
    )
    task.syncStatusFromStages()
    return task


__all__ = [
    "BilibiliDownloadStage",
    "BilibiliEpisodeFile",
    "BilibiliMergeStage",
    "BilibiliTask",
    "createBilibiliTask",
]
