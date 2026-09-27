from __future__ import annotations

import asyncio
import importlib
import io
import shutil
import tempfile
import threading
from collections.abc import Iterable, Iterator
from contextlib import suppress
from dataclasses import dataclass, field
from itertools import count
from pathlib import Path
from time import time
from urllib.parse import parse_qs, urlparse

from loguru import logger

from app.models.task import SpecialFileSize, Task, TaskError, TaskFile, TaskStep, TaskStatus, deletePlaceholder
from app.platform.filesystem import splitStemExt, toSafeFilename
from ffmpeg_pack.task import FFmpegResourceStep, FFmpegStep
from http_pack.task import HttpTaskStep

ERROR_HINTS = (
    ("is not available in your country", "该视频在您所在地区不可用，请尝试配置代理（{detail}）"),
    ("video unavailable", "视频不可用，可能已被删除或设为私密（{detail}）"),
    ("private video", "私密视频，需要已授权账号的 Cookie。请通过浏览器扩展下载或在设置中手动导入 Cookie（{detail}）"),
    ("members-only", "会员专属视频，需要会员账号的 Cookie。请通过浏览器扩展下载或在设置中手动导入 Cookie（{detail}）"),
    ("confirm your age", "年龄限制视频，需要登录。请通过浏览器扩展下载或在设置中手动导入 Cookie（{detail}）"),
    ("confirm you're not a bot", "YouTube 需要人机验证。请通过浏览器扩展下载或在设置中手动导入 Cookie（{detail}）"),
    ("requested format is not available", "请求的格式不可用，请稍后重试（{detail}）"),
    ("http error 403", "下载被拒绝（403），链接可能已失效（{detail}）"),
)

_pathLock = threading.Lock()
_pathInserted = False


def loadYtDlpToPath() -> None:
    global _pathInserted
    if _pathInserted:
        return
    with _pathLock:
        if _pathInserted:
            return
        import sys
        from .config import youTubeRuntime
        vendorPath = str(youTubeRuntime.ytDlpFolder())
        if vendorPath and vendorPath not in sys.path:
            sys.path.insert(0, vendorPath)
        _pathInserted = True


def buildYtDlpOptions(*, noplaylist: bool = True) -> dict:
    from .config import cookieFile, hasCookieFile, youTubeRuntime
    from app.config.cfg import cfg, proxy

    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "allowed_extractors": ["youtube.*"],
        "remote_components": {"ejs:github"},
        "nocheckcertificate": not cfg.shouldVerifySsl.value,
    }
    if noplaylist:
        opts["noplaylist"] = True
    qjsPath = youTubeRuntime.qjsPath()
    if qjsPath:
        opts["js_runtimes"] = {"quickjs": {"path": qjsPath}}
    proxyUrl = proxy()
    if proxyUrl:
        opts["proxy"] = proxyUrl
    if hasCookieFile():
        opts["cookiefile"] = io.StringIO(cookieFile().read_text(encoding="utf-8"))
    return opts


def probeFormats(url: str) -> dict:
    loadYtDlpToPath()
    yt_dlp = importlib.import_module("yt_dlp")
    opts = buildYtDlpOptions()
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def probePlaylist(url: str) -> list[dict]:
    loadYtDlpToPath()
    yt_dlp = importlib.import_module("yt_dlp")
    opts = buildYtDlpOptions(noplaylist=False)
    opts["extract_flat"] = True
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = info.get("entries") or []
    return [
        {"id": e.get("id") or "", "title": e.get("title") or "", "duration": e.get("duration") or 0}
        for e in entries if e and e.get("id")
    ]


DIRECT_PROTOCOLS = {"https", "http"}


def buildFormatPair(info: dict, task: YouTubeTask) -> tuple[dict | None, dict | None]:
    from .config import ytDlpConfig
    formats = [f for f in (info.get("formats") or []) if f.get("protocol") in DIRECT_PROTOCOLS]
    shouldPreferMp4 = ytDlpConfig.shouldPreferMp4.value

    audioFormats = [
        f for f in formats
        if f.get("acodec", "none") != "none"
        and f.get("vcodec", "none") == "none"
    ]

    primaryLang = next(iter(parseLanguages(task.audioLanguages)), "")
    if primaryLang:
        langFormats = [f for f in audioFormats if f.get("language") == primaryLang]
        if langFormats:
            audioFormats = langFormats
        else:
            logger.warning("audio language '{}' not available, falling back to original", primaryLang)
            origFormats = [f for f in audioFormats if (f.get("language_preference") or 0) >= 10]
            audioFormats = origFormats or audioFormats
    else:
        origFormats = [f for f in audioFormats if (f.get("language_preference") or 0) >= 10]
        if origFormats:
            audioFormats = origFormats

    if task.maxAudioBitrate > 0:
        audioFormats = [f for f in audioFormats
                       if (f.get("abr") or f.get("tbr") or 0) <= task.maxAudioBitrate]

    audioFormats.sort(
        key=lambda f: (shouldPreferMp4 and f.get("ext") in ("mp4", "m4a"), f.get("abr") or f.get("tbr") or 0),
        reverse=True,
    )
    audioFmt = audioFormats[0] if audioFormats else None

    if not task.isVideoEnabled:
        return None, audioFmt if task.isAudioEnabled else None

    if not task.isAudioEnabled:
        audioFmt = None

    videoFormats = [
        f for f in formats
        if f.get("vcodec", "none") != "none"
        and f.get("acodec", "none") == "none"
    ]

    if task.maxVideoHeight > 0:
        videoFormats = [f for f in videoFormats if (f.get("height") or 0) <= task.maxVideoHeight]

    videoFormats.sort(
        key=lambda f: (shouldPreferMp4 and f.get("ext") in ("mp4", "m4a"), f.get("height") or 0, f.get("tbr") or 0),
        reverse=True,
    )
    videoFmt = videoFormats[0] if videoFormats else None

    if not videoFmt:
        combined = [f for f in formats if f.get("vcodec", "none") != "none"]
        combined.sort(
            key=lambda f: (f.get("height") or 0, f.get("tbr") or 0),
            reverse=True,
        )
        if combined:
            videoFmt = combined[0]

    return videoFmt, audioFmt


@dataclass(kw_only=True)
class YouTubeFile(TaskFile):
    videoId: str = ""
    duration: int = 0
    startTime: int = 0
    endTime: int = 0


def parseLanguages(value: str) -> list[str]:
    return [s.strip() for s in value.split(",") if s.strip()]


def buildStepGroup(task: YouTubeTask, fileIndex: int, stepIndexes: Iterator[int], videoUrl: str = "") -> list[TaskStep]:
    steps: list[TaskStep] = [
        YouTubeExtractStep(stepIndex=next(stepIndexes), fileIndex=fileIndex, videoUrl=videoUrl),
        YouTubeResourceStep(stepIndex=next(stepIndexes), fileIndex=fileIndex, role="video"),
        YouTubeResourceStep(stepIndex=next(stepIndexes), fileIndex=fileIndex, role="audio"),
        YouTubeMergeStep(stepIndex=next(stepIndexes), fileIndex=fileIndex, videoUrl=videoUrl),
    ]
    if task.isVideoEnabled or task.isAudioEnabled:
        for language in parseLanguages(task.subtitleLanguages):
            steps.append(YouTubeSubtitleStep(stepIndex=next(stepIndexes), fileIndex=fileIndex, language=language))
    if task.isAudioEnabled:
        for language in parseLanguages(task.audioLanguages)[1:]:
            steps.append(YouTubeResourceStep(
                stepIndex=next(stepIndexes), fileIndex=fileIndex, role="audio", language=language))
            steps.append(YouTubeMergeStep(stepIndex=next(stepIndexes), fileIndex=fileIndex, language=language))
    return steps


def toResourcePath(task: Task, fileIndex: int, role: str, language: str, extension: str) -> Path:
    extension = extension or ("m4a" if language else "")
    kind = f"{language}.audio" if language else role
    suffix = f"{kind}.{extension}" if extension else kind
    return task.partPath / task.toSidePath(fileIndex, suffix).name


@dataclass(kw_only=True, eq=False)
class YouTubeTask(Task):
    packId: str = "ytdlp"
    canEdit = True
    fileType = YouTubeFile
    maxVideoHeight: int = 0
    maxAudioBitrate: int = 0
    isVideoEnabled: bool = True
    isAudioEnabled: bool = True
    audioLanguages: str = ""
    subtitleLanguages: str = ""
    shouldIncludeAutoSubs: bool = False
    coverUrl: str = ""
    isCoverEnabled: bool = False
    isPlaylist: bool = False

    def __post_init__(self):
        super().__post_init__()
        if any(isinstance(s, YouTubeSubtitleStep) and not s.language for s in self.steps):
            self.updateSteps()

    def setTracks(self, isVideoEnabled: bool, isAudioEnabled: bool, isCoverEnabled: bool) -> None:
        if (isVideoEnabled, isAudioEnabled, isCoverEnabled) == (self.isVideoEnabled, self.isAudioEnabled, self.isCoverEnabled):
            return
        self.isVideoEnabled, self.isAudioEnabled, self.isCoverEnabled = isVideoEnabled, isAudioEnabled, isCoverEnabled
        extension = "mp4" if isVideoEnabled else "m4a" if isAudioEnabled else "jpg" if isCoverEnabled else ""
        if extension:
            self.setName(f"{splitStemExt(self.name)[0]}.{extension}")
        self.updateSteps()

    def setAudioLanguages(self, languages: str) -> None:
        self.audioLanguages = languages
        self.updateSteps()

    def setSubtitleLanguages(self, languages: str, shouldIncludeAutoSubs: bool) -> None:
        self.subtitleLanguages = languages
        self.shouldIncludeAutoSubs = shouldIncludeAutoSubs
        self.updateSteps()

    def setCoverUrl(self, url: str) -> None:
        if url:
            self.coverUrl = url
            self.updateSteps()

    def setVideos(self, videos: list[dict]) -> None:
        extension = "mp4" if self.isVideoEnabled else "m4a"
        taken: set[str] = set()
        self.files = []
        for i, video in enumerate(videos):
            name = f"{toSafeFilename(str(video.get('title') or f'视频 {i + 1}'))}.{extension}"
            stem, ext = splitStemExt(name)
            index = 0
            while name.lower() in taken:
                index += 1
                name = f"{stem}({index}){ext}"
            taken.add(name.lower())
            self.files.append(YouTubeFile(
                index=i,
                relativePath=name,
                videoId=str(video.get("id") or ""),
                duration=int(video.get("duration") or 0),
            ))
        self.updateSteps()

    def toDisplayPath(self, file: YouTubeFile) -> str:
        return splitStemExt(file.relativePath)[0]

    def updateSteps(self) -> None:
        extension = "mp4" if self.isVideoEnabled else "m4a"
        for file in self.files or []:
            stem, _ = splitStemExt(file.relativePath)
            file.relativePath = f"{stem}.{extension}"
        stepIndexes = count()
        steps = [step for file in self.files or []
                 for step in buildStepGroup(self, file.index, stepIndexes, f"https://www.youtube.com/watch?v={file.videoId}")]
        steps = steps or buildStepGroup(self, 0, stepIndexes)
        steps.append(YouTubeCoverStep(
            stepIndex=next(stepIndexes),
            url=self.coverUrl,
            canUseRangeRequests=False,
            subworkerCount=1,
        ))
        for step in steps:
            step._bindTask(self)
        self.steps = steps
        self.updateStatus()

    def setSelection(self, selectedIndexes) -> None:
        super().setSelection(selectedIndexes)
        # 视频大小在 extract 前未知，files 的 size 恒为 0，改从资源步骤汇总
        totalSize = sum(
            s.fileSize for s in self.steps
            if isinstance(s, FFmpegResourceStep) and self._isStepSelected(s)
        )
        self.fileSize = totalSize if totalSize > 0 else int(SpecialFileSize.UNKNOWN)

    def pendingSteps(self) -> Iterable[TaskStep]:
        self.steps.sort(key=lambda step: step.stepIndex)
        for step in self.steps:
            if self.status != TaskStatus.RUNNING:
                break
            if not self._isStepSelected(step):
                continue
            if isinstance(step, YouTubeExtractStep):
                yield step
                continue
            if step.status == TaskStatus.COMPLETED:
                continue
            yield step

    def currentSnapshot(self) -> tuple[float, int, int]:
        downloadSteps = [
            s for s in self.steps
            if not isinstance(s, YouTubeExtractStep) and self._isStepSelected(s)
        ]
        if not downloadSteps:
            return 0.0, 0, 0
        completedCount = sum(1 for s in downloadSteps if s.status == TaskStatus.COMPLETED)
        currentStep = next((s for s in downloadSteps if s.status == TaskStatus.RUNNING), None)
        totalCount = len(downloadSteps)
        if currentStep:
            progress = (completedCount * 100 + currentStep.progress) / totalCount
            speed = currentStep.speed
        else:
            progress = completedCount * 100 / totalCount if totalCount else 0
            speed = 0
        receivedBytes = sum(s.receivedBytes for s in downloadSteps)
        return progress, speed, receivedBytes


@dataclass(kw_only=True)
class YouTubeExtractStep(TaskStep):
    canPause = False
    fileIndex: int = 0
    videoUrl: str = ""

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        if not self.task.isVideoEnabled and not self.task.isAudioEnabled:
            return

        if self._hasFreshSiblingUrls():
            return

        from .config import youTubeRuntime
        if not youTubeRuntime.path():
            raise TaskError("{name} 未安装，请在设置中安装", name=youTubeRuntime.name)

        url = self.videoUrl or self.task.url
        try:
            info = await asyncio.to_thread(probeFormats, url)
        except Exception as e:
            logger.opt(exception=e).warning("extract_info failed for {}", url)
            detail = str(e)
            lowered = detail.lower()
            hint = next((h for needle, h in ERROR_HINTS if needle in lowered), "")
            if hint:
                raise TaskError(hint, detail=detail)
            raise TaskError("视频信息提取失败：{detail}", detail=detail or "unknown")

        videoFmt, audioFmt = buildFormatPair(info, self.task)
        if not videoFmt and not audioFmt:
            logger.warning("no formats found for {} (formats count: {})", url, len(info.get("formats") or []))
            raise TaskError("未找到可用的视频格式")

        self._updateSiblingSteps(videoFmt, audioFmt, info)
        logger.info("selected video={} audio={} for {}",
                     videoFmt.get("format_id") if videoFmt else None,
                     audioFmt.get("format_id") if audioFmt else None, url)

        file = self.task.files[self.fileIndex] if self.task.files else None
        if file and (file.startTime or file.endTime):
            await self._updateSegmentRanges(file)

        self._updateSubtitleSteps(info)

    def _updateSubtitleSteps(self, info: dict) -> None:
        from .config import loadCookieHeader
        cookieHeader = loadCookieHeader()
        for step in self.task.steps:
            if not isinstance(step, YouTubeSubtitleStep) or step.fileIndex != self.fileIndex:
                continue
            formats = (info.get("subtitles") or {}).get(step.language)
            if not formats and self.task.shouldIncludeAutoSubs:
                formats = (info.get("automatic_captions") or {}).get(step.language)
            subtitle = next((f for f in formats or [] if f.get("ext") == "vtt" and f.get("url")), None)
            step.url = subtitle["url"] if subtitle else ""
            step.headers = {"cookie": cookieHeader} if cookieHeader else {}

    def _hasFreshSiblingUrls(self) -> bool:
        now = time()
        for s in self.task.steps:
            if not isinstance(s, YouTubeResourceStep) or s.fileIndex != self.fileIndex:
                continue
            if not s.url:
                continue
            expireValues = parse_qs(urlparse(s.url).query).get("expire", [])
            try:
                if now < int(expireValues[0]) - 60:
                    return True
            except (ValueError, IndexError):
                continue
        return False

    async def _updateSegmentRanges(self, file: YouTubeFile) -> None:
        from app.client import buildClient, toEmulation
        from app.config.cfg import cfg
        from app.container import buildMp4SegmentRange, buildWebmSegmentRange

        for step in self.task.steps:
            if step.fileIndex != self.fileIndex or not isinstance(step, YouTubeResourceStep):
                continue
            if not step.url:
                continue
            emulation = toEmulation(step.clientProfile or cfg.clientProfile.value, "")
            client = buildClient(emulation=emulation, userAgent=step.userAgent or None)
            try:
                headers = {**step.headers, "range": "bytes=0-4095", "accept-encoding": "identity"}
                response = await client.get(step.url, headers=headers)
                try:
                    headerData = await response.bytes()
                finally:
                    response.close()
            finally:
                client.close()

            isWebm = step.extension in ("webm", "mkv")
            builder = buildWebmSegmentRange if isWebm else buildMp4SegmentRange
            try:
                segRange = builder(headerData, file.startTime, file.endTime)
            except Exception as e:
                logger.warning("segment range parsing failed for {}: {}", step.url, e)
                continue

            step.httpByteOffset = segRange.segStart
            step.fileSize = segRange.segEnd - segRange.segStart

            stepLang = step.language
            for mergeStep in self.task.steps:
                if (isinstance(mergeStep, YouTubeMergeStep)
                        and mergeStep.fileIndex == self.fileIndex
                        and mergeStep.language == stepLang):
                    if step.role == "video" and not stepLang:
                        mergeStep.patchedVideoHeader = segRange.patchedHeader
                    else:
                        mergeStep.patchedAudioHeader = segRange.patchedHeader
                    mergeStep.segStartTime = segRange.segStartTime
                    break

        totalSize = sum(
            s.fileSize for s in self.task.steps
            if isinstance(s, FFmpegResourceStep) and self.task._isStepSelected(s)
        )
        self.task.fileSize = totalSize if totalSize > 0 else 0

    def _updateSiblingSteps(self, videoFmt: dict | None, audioFmt: dict | None, info: dict) -> None:
        from app.config.cfg import cfg
        from .config import ytDlpConfig

        for step in self.task.steps:
            if step.fileIndex != self.fileIndex:
                continue
            if isinstance(step, YouTubeResourceStep) and step.language:
                continue
            if isinstance(step, FFmpegResourceStep):
                fmt = videoFmt if step.role == "video" else audioFmt
                if not fmt:
                    step.url = ""
                    continue
                step.url = fmt["url"]
                step.fileSize = fmt.get("filesize") or fmt.get("filesize_approx") or 0
                step.extension = fmt.get("ext") or ("mp4" if step.role == "video" else "m4a")
                step.canUseRangeRequests = True
                step.subworkerCount = cfg.preBlockNum.value
                step.headers = dict(fmt.get("http_headers") or {})
            elif isinstance(step, YouTubeMergeStep) and not step.language:
                step.videoExtension = videoFmt.get("ext", "mp4") if videoFmt else ""
                step.audioExtension = audioFmt.get("ext", "m4a") if audioFmt else ""
                if ytDlpConfig.shouldEmbedMetadata.value:
                    step.metadataTitle = info.get("title") or ""
                    step.metadataArtist = info.get("uploader") or info.get("channel") or ""
                if ytDlpConfig.shouldEmbedChapters.value:
                    step.chapters = info.get("chapters") or []

        self._updateExtraAudioSteps(info, cfg.preBlockNum.value)

        totalSize = sum(
            s.fileSize for s in self.task.steps
            if isinstance(s, FFmpegResourceStep) and self.task._isStepSelected(s)
        )
        self.task.fileSize = totalSize if totalSize > 0 else 0

    def _updateExtraAudioSteps(self, info: dict, subworkerCount: int) -> None:
        from .config import ytDlpConfig

        formats = [f for f in (info.get("formats") or []) if f.get("protocol") in DIRECT_PROTOCOLS]
        audioFormats = [
            f for f in formats
            if f.get("acodec", "none") != "none" and f.get("vcodec", "none") == "none"
        ]
        shouldPreferMp4 = ytDlpConfig.shouldPreferMp4.value

        for step in self.task.steps:
            if not isinstance(step, YouTubeResourceStep) or not step.language or step.fileIndex != self.fileIndex:
                continue
            langFormats = sorted(
                (f for f in audioFormats if f.get("language") == step.language),
                key=lambda f: (
                    shouldPreferMp4 and f.get("ext") in ("mp4", "m4a"),
                    f.get("abr") or f.get("tbr") or 0,
                ),
                reverse=True,
            )
            if not langFormats:
                logger.warning("audio language '{}' not available for extra track, skipping", step.language)
                step.url = ""
                continue
            fmt = langFormats[0]
            step.url = fmt["url"]
            step.fileSize = fmt.get("filesize") or fmt.get("filesize_approx") or 0
            step.extension = fmt.get("ext") or "m4a"
            step.canUseRangeRequests = True
            step.subworkerCount = subworkerCount
            step.headers = dict(fmt.get("http_headers") or {})
            for merge in self.task.steps:
                if (isinstance(merge, YouTubeMergeStep) and merge.language == step.language
                        and merge.fileIndex == self.fileIndex):
                    merge.audioExtension = step.extension


@dataclass(kw_only=True)
class YouTubeResourceStep(FFmpegResourceStep):
    fileIndex: int = 0
    language: str = ""

    @property
    def outputPath(self) -> str:
        return str(toResourcePath(self.task, self.fileIndex, self.role, self.language, self.extension))

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        if self.url:
            await super().run(reportSpeed, waitForSpeedLimit)


@dataclass(kw_only=True)
class YouTubeSubtitleStep(HttpTaskStep):
    fileIndex: int = 0
    language: str = ""
    canUseRangeRequests: bool = False
    subworkerCount: int = 1

    @property
    def outputPath(self) -> str:
        return str(self.task.toSidePath(self.fileIndex, f"{toSafeFilename(self.language, fallback='subtitle')}.vtt"))

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        if self.url:
            await super().run(reportSpeed, waitForSpeedLimit)
        else:
            deletePlaceholder(Path(self.outputPath))


@dataclass(kw_only=True)
class YouTubeMergeStep(FFmpegStep):
    fileIndex: int = 0
    videoUrl: str = ""
    language: str = ""
    metadataTitle: str = ""
    metadataArtist: str = ""
    chapters: list[dict] = field(default_factory=list)
    patchedVideoHeader: bytes = field(default=b"", repr=False)
    patchedAudioHeader: bytes = field(default=b"", repr=False)
    segStartTime: float = field(default=0.0, repr=False)

    @property
    def outputPath(self) -> str:
        if self.language:
            return str(self.task.toSidePath(self.fileIndex, f"{self.language}.m4a"))
        return str(self.task.toFilePath(self.fileIndex))

    @property
    def _videoPath(self) -> Path:
        return toResourcePath(self.task, self.fileIndex, "video", "", self.videoExtension)

    @property
    def _audioPath(self) -> Path:
        return toResourcePath(self.task, self.fileIndex, "audio", self.language, self.audioExtension)

    @property
    def _timeRange(self) -> tuple[int, int] | None:
        if not self.task.files:
            return None
        for f in self.task.files:
            if f.index == self.fileIndex and (f.startTime or f.endTime):
                return f.startTime, f.endTime
        return None

    def _buildTrimArgs(self) -> tuple[list[str], list[str]]:
        tr = self._timeRange
        if not tr:
            return [], []
        relSS = tr[0] - self.segStartTime
        return ["-ss", str(relSS)], ["-t", str(tr[1] - tr[0])]

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        for header, path in [
            (self.patchedVideoHeader, self._videoPath),
            (self.patchedAudioHeader, self._audioPath),
        ]:
            if header and path.exists():
                tmp = path.with_suffix(".tmp")
                with open(tmp, "wb") as f:
                    f.write(header)
                    with open(path, "rb") as seg:
                        shutil.copyfileobj(seg, f)
                tmp.replace(path)

        hasVideo = self._videoPath.exists()
        hasAudio = self._audioPath.exists()

        if hasVideo and hasAudio:
            if self.metadataTitle or self.chapters or self._timeRange:
                await self._runWithMetadata()
            else:
                await super().run(reportSpeed, waitForSpeedLimit)
            return

        singleInput = self._videoPath if hasVideo else self._audioPath if hasAudio else None
        if not singleInput:
            deletePlaceholder(Path(self.outputPath))
            return

        isSameContainer = singleInput.suffix.lower() == Path(self.outputPath).suffix.lower()
        if isSameContainer and not (self.metadataTitle or self.chapters or self._timeRange):
            singleInput.replace(self.outputPath)
        else:
            await self._runSingleWithMetadata(singleInput)

    async def _runSingleWithMetadata(self, inputPath: Path) -> None:
        from ffmpeg_pack.config import ffmpegRuntime
        from app.platform.filesystem import deletePath

        ffmpegPath = ffmpegRuntime.path()
        ffprobePath = ffmpegRuntime.ffprobePath()
        if not ffmpegPath or not ffprobePath:
            raise TaskError("{name} 未安装，请在设置中安装", name="FFmpeg")

        totalDuration = await self._probeDuration(ffprobePath, inputPath)

        preArgs, postArgs = self._buildTrimArgs()
        args = [
            ffmpegPath,
            "-y", "-v", "error", "-nostats", "-progress", "pipe:1",
            *preArgs,
            "-i", str(inputPath),
        ]

        chaptersFile = None
        if self.chapters:
            chaptersFile = self._createChaptersFile()
            args.extend(["-f", "ffmetadata", "-i", chaptersFile])

        args.extend(postArgs)

        args.extend(["-c", "copy"])

        if self.chapters and chaptersFile:
            args.extend(["-map", "0", "-map_metadata", "1"])

        if self.metadataTitle:
            args.extend(["-metadata", f"title={self.metadataTitle}"])
        if self.metadataArtist:
            args.extend(["-metadata", f"artist={self.metadataArtist}"])

        args.extend(["-f", "mp4", self.outputPath])

        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        progressTask = asyncio.create_task(self._readProgress(process.stdout, totalDuration))

        try:
            await process.wait()
            await progressTask

            if process.returncode != 0:
                stderr = (await process.stderr.read()).decode("utf-8", errors="ignore").strip()
                raise TaskError(
                    "FFmpeg 写入元数据失败（{code}）：{detail}",
                    code=process.returncode,
                    detail=stderr or "unknown error",
                )

            if self.shouldDeleteSource:
                deletePath(inputPath)
        except asyncio.CancelledError:
            self.setStatus(TaskStatus.PAUSED)
            if process.returncode is None:
                process.kill()
                await process.wait()
            if not progressTask.done():
                progressTask.cancel()
                with suppress(asyncio.CancelledError):
                    await progressTask
            raise
        finally:
            if chaptersFile:
                Path(chaptersFile).unlink(missing_ok=True)

    async def _runWithMetadata(self) -> None:
        from ffmpeg_pack.config import ffmpegRuntime
        from app.platform.filesystem import deletePath

        ffmpegPath = ffmpegRuntime.path()
        ffprobePath = ffmpegRuntime.ffprobePath()
        if not ffmpegPath or not ffprobePath:
            raise TaskError("{name} 未安装，请在设置中安装", name="FFmpeg")

        totalDuration = await self._probeDuration(ffprobePath, self._videoPath)

        preArgs, postArgs = self._buildTrimArgs()
        args = [
            ffmpegPath,
            "-y", "-v", "error", "-nostats", "-progress", "pipe:1",
            *preArgs,
            "-i", str(self._videoPath),
            *preArgs,
            "-i", str(self._audioPath),
        ]

        chaptersFile = None
        if self.chapters:
            chaptersFile = self._createChaptersFile()
            args.extend(["-f", "ffmetadata", "-i", chaptersFile])

        args.extend(postArgs)

        args.extend(["-c", "copy"])

        if self.chapters and chaptersFile:
            args.extend(["-map", "0", "-map", "1", "-map_metadata", "2"])

        if self.metadataTitle:
            args.extend(["-metadata", f"title={self.metadataTitle}"])
        if self.metadataArtist:
            args.extend(["-metadata", f"artist={self.metadataArtist}"])

        args.extend(["-f", "mp4", self.outputPath])

        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        progressTask = asyncio.create_task(self._readProgress(process.stdout, totalDuration))

        try:
            await process.wait()
            await progressTask

            if process.returncode != 0:
                stderr = (await process.stderr.read()).decode("utf-8", errors="ignore").strip()
                raise TaskError(
                    "FFmpeg 合并失败（{code}）：{detail}",
                    code=process.returncode,
                    detail=stderr or "unknown error",
                )

            if self.shouldDeleteSource:
                for path in (self._videoPath, self._audioPath):
                    deletePath(path)
        except asyncio.CancelledError:
            self.setStatus(TaskStatus.PAUSED)
            if process.returncode is None:
                process.kill()
                await process.wait()
            if not progressTask.done():
                progressTask.cancel()
                with suppress(asyncio.CancelledError):
                    await progressTask
            raise
        finally:
            if chaptersFile:
                Path(chaptersFile).unlink(missing_ok=True)

    def _createChaptersFile(self) -> str:
        lines = [";FFMETADATA1"]
        for ch in self.chapters:
            start = int(ch.get("start_time", 0) * 1000)
            end = int(ch.get("end_time", 0) * 1000)
            title = str(ch.get("title", "")).replace("=", "\\=").replace(";", "\\;").replace("#", "\\#")
            lines.append("[CHAPTER]")
            lines.append("TIMEBASE=1/1000")
            lines.append(f"START={start}")
            lines.append(f"END={end}")
            lines.append(f"title={title}")
        fd, path = tempfile.mkstemp(suffix=".txt", prefix="chapters_", dir=self.task.partPath)
        with open(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return path


@dataclass(kw_only=True)
class YouTubeCoverStep(HttpTaskStep):

    @property
    def outputPath(self) -> str:
        if not self.task.isCoverEnabled:
            return ""
        return str(self.task.toSidePath(None, "jpg"))

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        if self.url:
            await super().run(reportSpeed, waitForSpeedLimit)
