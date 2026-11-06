from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from app.models.pack import BinaryRuntime, FeaturePack, TaskParser
from app.models.task import (
    MergeTaskOptions,
    RemoteFile,
    ResourceTaskOptions,
    Task,
    TaskOptions,
)
from app.platform.filesystem import toSafeFilename
from http_pack.pack import buildEditCards, buildOptionCards, buildStep, probe
from .config import ffmpegConfig, ffmpegRuntime
from .task import FFmpegResourceStep, FFmpegStep, FFmpegTask, probeContainerIndex

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
    from app.view.cards.draft_cards import DraftCard
    from app.view.cards.task_cards import TaskCard
    from app.view.components.option_cards import OptionCard

VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".webm"}
VIDEO_CONTENT_TYPES = {"video/mp4", "video/x-m4v", "video/quicktime", "video/webm"}


async def resolveResourceFile(options: ResourceTaskOptions) -> RemoteFile:
    if options.file is not None:
        return options.file
    if options.name and options.size > 0:
        return RemoteFile(
            name=options.name,
            fileSize=options.size,
            canUseRangeRequests=options.canUseRangeRequests,
        )
    return await probe(options)


class MergeParser(TaskParser):
    priority = 60

    def match(self, options: TaskOptions) -> bool:
        return isinstance(options, MergeTaskOptions)

    async def parse(self, options: TaskOptions) -> Task:
        assert isinstance(options, MergeTaskOptions)
        assert options.video is not None and options.audio is not None

        videoFile = await resolveResourceFile(options.video)
        audioFile = await resolveResourceFile(options.audio)

        videoExt = Path(videoFile.name or urlparse(options.video.url).path).suffix.lstrip(".").lower() or "mp4"
        audioExt = Path(audioFile.name or urlparse(options.audio.url).path).suffix.lstrip(".").lower() or "m4a"

        rawName = options.video.name or videoFile.name
        stem = toSafeFilename(rawName, fallback="merged-media")
        name = stem if stem.lower().endswith(".mp4") else f"{stem}.mp4"

        videoData = b""
        videoIndex = None
        if videoFile.canUseRangeRequests:
            with suppress(Exception):
                probed = await probeContainerIndex(
                    options.video.url,
                    videoFile.fileSize,
                    headers=options.video.headers,
                    clientProfile=options.video.clientProfile,
                    userAgent=options.video.userAgent,
                    sourceUserAgent=options.video.sourceUserAgent,
                )
                if probed is not None:
                    videoData, videoIndex = probed

        audioData = b""
        audioIndex = None
        if audioFile.canUseRangeRequests and videoIndex is not None:
            with suppress(Exception):
                probed = await probeContainerIndex(
                    options.audio.url,
                    audioFile.fileSize,
                    headers=options.audio.headers,
                    clientProfile=options.audio.clientProfile,
                    userAgent=options.audio.userAgent,
                    sourceUserAgent=options.audio.sourceUserAgent,
                )
                if probed is not None:
                    audioData, audioIndex = probed

        totalSize = max(0, videoFile.fileSize) + max(0, audioFile.fileSize)
        duration = int(videoIndex.duration) if videoIndex is not None else 0

        videoStep = buildStep(
            FFmpegResourceStep,
            1,
            options.video.url,
            options.video,
            videoFile,
            role="video",
            extension=videoExt,
            rawFileSize=max(0, videoFile.fileSize),
            headerData=videoData,
            containerIndex=videoIndex,
        )
        audioStep = buildStep(
            FFmpegResourceStep,
            2,
            options.audio.url,
            options.audio,
            audioFile,
            role="audio",
            extension=audioExt,
            rawFileSize=max(0, audioFile.fileSize),
            headerData=audioData,
            containerIndex=audioIndex,
        )
        ffmpegStep = FFmpegStep(
            stepIndex=3,
            videoExtension=videoExt,
            audioExtension=audioExt,
        )
        return FFmpegTask(
            name=name,
            url=options.video.url,
            fileSize=totalSize,
            rawFileSize=totalSize,
            outputFolder=options.outputFolder,
            duration=duration,
            videoData=videoData,
            videoIndex=videoIndex,
            audioData=audioData,
            audioIndex=audioIndex,
            steps=[videoStep, audioStep, ffmpegStep],
        )


class VideoParser(TaskParser):
    priority = 97

    def match(self, options: TaskOptions) -> bool:
        return (
            options.isProbed
            and options.file.canUseRangeRequests
            and options.file.fileSize > 0
            and options.file.matchType(VIDEO_EXTENSIONS, VIDEO_CONTENT_TYPES)
        )

    async def parse(self, options: TaskOptions) -> Task:
        file = options.file
        assert file is not None
        probed = await probeContainerIndex(
            options.url,
            file.fileSize,
            headers=options.headers,
            clientProfile=options.clientProfile,
            userAgent=options.userAgent,
            sourceUserAgent=options.sourceUserAgent,
        )
        if probed is None:
            raise ValueError("无法解析视频容器索引")
        videoData, videoIndex = probed
        duration = int(videoIndex.duration)
        if duration <= 0:
            raise ValueError("视频时长无效")

        name = options.name if isinstance(options, ResourceTaskOptions) and options.name else file.name
        name = toSafeFilename(name, fallback="video.mp4")
        videoExt = Path(name).suffix.lstrip(".").lower() or ("webm" if videoIndex.format == "webm" else "mp4")

        videoStep = buildStep(
            FFmpegResourceStep,
            1,
            options.url,
            options,
            file,
            role="video",
            extension=videoExt,
            rawFileSize=file.fileSize,
            headerData=videoData,
            containerIndex=videoIndex,
        )
        ffmpegStep = FFmpegStep(
            stepIndex=2,
            videoExtension=videoExt,
        )
        return FFmpegTask(
            name=name,
            url=options.url,
            fileSize=file.fileSize,
            rawFileSize=file.fileSize,
            outputFolder=options.outputFolder,
            duration=duration,
            videoData=videoData,
            videoIndex=videoIndex,
            steps=[videoStep, ffmpegStep],
        )


class FFmpegPack(FeaturePack):
    packId = "ffmpeg"
    config = ffmpegConfig
    parsers = [MergeParser, VideoParser]

    def runtimes(self) -> list[BinaryRuntime]:
        return [ffmpegRuntime]

    def taskCardClass(self, task: Task) -> type[TaskCard] | None:
        from http_pack.cards import HttpTaskCard
        return HttpTaskCard

    def draftCardClass(self, task: Task) -> type[DraftCard] | None:
        from .cards import FFmpegDraftCard
        return FFmpegDraftCard

    def optionCards(self, task: Task, parent: QWidget | None = None) -> list[OptionCard]:
        return buildOptionCards(task, parent)

    def editCards(self, task: Task, parent: QWidget | None = None) -> list[OptionCard]:
        if isinstance(task, FFmpegTask) and task.hasAudio:
            return buildOptionCards(task, parent)
        return buildEditCards(task, parent)
