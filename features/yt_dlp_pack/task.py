from __future__ import annotations

import asyncio
import importlib
import io
import shutil
import tempfile
import threading
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from time import time
from urllib.parse import parse_qs, urlparse

from loguru import logger

from app.models.task import SpecialFileSize, Task, TaskError, TaskFile, TaskStep, TaskStatus
from ffmpeg_pack.task import FFmpegResourceStep, FFmpegStep, mediaStem
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

STEPS_PER_VIDEO = 5


def buildTimeSuffix(startTime: int, endTime: int) -> str:
    def fmt(sec: int) -> str:
        m, s = divmod(sec, 60)
        return f"{m:02d}m{s:02d}s"
    return f"[{fmt(startTime)}-{fmt(endTime)}]"

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


def buildStepGroup(fileIndex: int, videoUrl: str = "", videoStem: str = "") -> list[TaskStep]:
    base = fileIndex * STEPS_PER_VIDEO
    return [
        YouTubeExtractStep(stepIndex=base + 1, fileIndex=fileIndex, videoUrl=videoUrl),
        YouTubeResourceStep(stepIndex=base + 2, fileIndex=fileIndex, videoStem=videoStem, role="video"),
        YouTubeResourceStep(stepIndex=base + 3, fileIndex=fileIndex, videoStem=videoStem, role="audio"),
        YouTubeMergeStep(stepIndex=base + 4, fileIndex=fileIndex, videoUrl=videoUrl, videoStem=videoStem),
        YouTubeSubtitleStep(stepIndex=base + 5, fileIndex=fileIndex, videoUrl=videoUrl, videoStem=videoStem),
    ]


@dataclass(kw_only=True, eq=False)
class YouTubeTask(Task):
    packId: str = "ytdlp"
    canEdit = True
    fileType = YouTubeFile
    maxVideoHeight: int = 0
    maxAudioBitrate: int = 0
    isVideoEnabled: bool = True
    isAudioEnabled: bool = True
    subtitleLanguages: str = ""
    shouldIncludeAutoSubs: bool = False
    coverUrl: str = ""
    isCoverEnabled: bool = False
    isPlaylist: bool = False

    def setCoverUrl(self, url: str) -> None:
        if not url:
            return
        self.coverUrl = url
        if any(isinstance(s, YouTubeCoverStep) for s in self.steps):
            return
        stepIndex = max((s.stepIndex for s in self.steps), default=0) + 1
        self.addStep(YouTubeCoverStep(
            stepIndex=stepIndex,
            url=url,
            fileSize=0,
            headers={},
            canUseRangeRequests=False,
            subworkerCount=1,
        ))

    def setVideos(self, videos: list[dict]) -> None:
        from app.platform.filesystem import toSafeFilename
        self.files = [
            YouTubeFile(
                index=i,
                relativePath=toSafeFilename(str(video.get("title") or f"视频 {i + 1}")),
                videoId=str(video.get("id") or ""),
                duration=int(video.get("duration") or 0),
            )
            for i, video in enumerate(videos)
        ]
        self.steps.clear()
        for file in self.files:
            videoUrl = f"https://www.youtube.com/watch?v={file.videoId}"
            for step in buildStepGroup(file.index, videoUrl=videoUrl, videoStem=file.relativePath):
                self.addStep(step)
        if not self.steps:
            for step in buildStepGroup(0):
                self.addStep(step)
        if self.coverUrl:
            self.setCoverUrl(self.coverUrl)

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
            self.setStatus(TaskStatus.COMPLETED)
            return

        if self._hasFreshSiblingUrls():
            self.setStatus(TaskStatus.COMPLETED)
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

        title = info.get("title")
        if title:
            from app.platform.filesystem import toSafeFilename
            safeName = toSafeFilename(title)
            if safeName:
                suffix = ""
                if file and (file.startTime or file.endTime):
                    suffix = f" {buildTimeSuffix(file.startTime, file.endTime)}"
                if self.fileIndex == 0 and len(self.task.files or []) <= 1:
                    ext = "m4a" if not videoFmt else "mp4"
                    self.task.setName(f"{safeName}{suffix}.{ext}")
                for step in self.task.steps:
                    if step.fileIndex == self.fileIndex and hasattr(step, "videoStem"):
                        step.videoStem = f"{safeName}{suffix}" if suffix else safeName

        self.setStatus(TaskStatus.COMPLETED)

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

            for mergeStep in self.task.steps:
                if isinstance(mergeStep, YouTubeMergeStep) and mergeStep.fileIndex == self.fileIndex:
                    if step.role == "video":
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
            elif isinstance(step, YouTubeMergeStep):
                step.videoExtension = videoFmt.get("ext", "mp4") if videoFmt else ""
                step.audioExtension = audioFmt.get("ext", "m4a") if audioFmt else ""
                if ytDlpConfig.shouldEmbedMetadata.value:
                    step.metadataTitle = info.get("title") or ""
                    step.metadataArtist = info.get("uploader") or info.get("channel") or ""
                if ytDlpConfig.shouldEmbedChapters.value:
                    step.chapters = info.get("chapters") or []

        totalSize = sum(
            s.fileSize for s in self.task.steps
            if isinstance(s, FFmpegResourceStep) and self.task._isStepSelected(s)
        )
        self.task.fileSize = totalSize if totalSize > 0 else 0


@dataclass(kw_only=True)
class YouTubeResourceStep(FFmpegResourceStep):
    fileIndex: int = 0
    videoStem: str = ""

    @property
    def outputPath(self) -> str:
        stem = self.videoStem or mediaStem(self.task)
        suffix = f".{self.extension}" if self.extension else ""
        return str(self.task.outputFolder / f"{stem}.{self.role}{suffix}")

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        if not self.url:
            self.setStatus(TaskStatus.COMPLETED)
            return
        await super().run(reportSpeed, waitForSpeedLimit)


@dataclass(kw_only=True)
class YouTubeSubtitleStep(TaskStep):
    fileIndex: int = 0
    videoUrl: str = ""
    videoStem: str = ""

    @property
    def outputPath(self) -> str:
        return ""

    def deleteFiles(self) -> None:
        stem = self.videoStem or mediaStem(self.task)
        for path in self.task.outputFolder.glob(f"{stem}.*.vtt"):
            path.unlink(missing_ok=True)

    def moveFiles(self, oldFolder: Path, newFolder: Path) -> None:
        stem = self.videoStem or mediaStem(self.task)
        for path in oldFolder.glob(f"{stem}.*.vtt"):
            target = newFolder / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                shutil.move(str(path), str(target))

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        if not self.task.subtitleLanguages or (
            not self.task.isVideoEnabled and not self.task.isAudioEnabled
        ):
            self.setStatus(TaskStatus.COMPLETED)
            return

        from app.client import buildClient
        from app.platform.filesystem import toSafeFilename
        from .config import loadCookieHeader

        info = await asyncio.to_thread(probeFormats, self.videoUrl or self.task.url)
        languages = [s.strip() for s in self.task.subtitleLanguages.split(",") if s.strip()]
        stem = self.videoStem or mediaStem(self.task)
        outputFolder = self.task.outputFolder
        outputFolder.mkdir(parents=True, exist_ok=True)

        downloads = []
        for lang in languages:
            formats = (info.get("subtitles") or {}).get(lang)
            isAuto = False
            if not formats and self.task.shouldIncludeAutoSubs:
                formats = (info.get("automatic_captions") or {}).get(lang)
                isAuto = True
            if not formats:
                continue
            subtitle = next(
                (f for f in formats if f.get("ext") == "vtt" and f.get("url")),
                None,
            )
            if not subtitle:
                continue
            safeLang = toSafeFilename(lang, fallback="subtitle")
            autoSuffix = ".auto" if isAuto else ""
            vttFile = outputFolder / f"{stem}.{safeLang}{autoSuffix}.vtt"
            downloads.append((lang, subtitle["url"], vttFile))

        if not downloads:
            self.setStatus(TaskStatus.COMPLETED)
            return

        cookieHeader = loadCookieHeader()
        client = buildClient(headers={"cookie": cookieHeader} if cookieHeader else None)
        try:
            for i, (lang, url, vttFile) in enumerate(downloads):
                if vttFile.exists():
                    self.progress = (i + 1) / len(downloads) * 100
                    continue
                try:
                    response = await client.get(url)
                    try:
                        response.raise_for_status()
                        vttFile.write_bytes(await response.bytes())
                    finally:
                        response.close()
                except Exception:
                    logger.opt(exception=True).debug("Subtitle download failed: {}", lang)
                self.progress = (i + 1) / len(downloads) * 100
        finally:
            client.close()

        self.setStatus(TaskStatus.COMPLETED)


@dataclass(kw_only=True)
class YouTubeMergeStep(FFmpegStep):
    fileIndex: int = 0
    videoUrl: str = ""
    videoStem: str = ""
    metadataTitle: str = ""
    metadataArtist: str = ""
    chapters: list[dict] = field(default_factory=list)
    patchedVideoHeader: bytes = field(default=b"", repr=False)
    patchedAudioHeader: bytes = field(default=b"", repr=False)
    segStartTime: float = field(default=0.0, repr=False)

    @property
    def outputFile(self) -> str:
        stem = self.videoStem or mediaStem(self.task)
        ext = "mp4" if self.videoExtension else (self.audioExtension or "m4a")
        return str(self.task.outputFolder / f"{stem}.{ext}")

    @property
    def _videoPath(self) -> Path:
        stem = self.videoStem or mediaStem(self.task)
        suffix = f".{self.videoExtension}" if self.videoExtension else ""
        return self.task.outputFolder / f"{stem}.video{suffix}"

    @property
    def _audioPath(self) -> Path:
        stem = self.videoStem or mediaStem(self.task)
        suffix = f".{self.audioExtension}" if self.audioExtension else ""
        return self.task.outputFolder / f"{stem}.audio{suffix}"

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
            self.setStatus(TaskStatus.COMPLETED)
            return

        if self.metadataTitle or self.chapters or self._timeRange:
            await self._runSingleWithMetadata(singleInput)
        else:
            outputPath = Path(self.outputFile)
            outputPath.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(singleInput), str(outputPath))
            Path(f"{singleInput}.ghd").unlink(missing_ok=True)
            self.setStatus(TaskStatus.COMPLETED)

    async def _runSingleWithMetadata(self, inputPath: Path) -> None:
        from ffmpeg_pack.config import ffmpegRuntime
        from app.platform.filesystem import deletePath

        ffmpegPath = ffmpegRuntime.path()
        ffprobePath = ffmpegRuntime.ffprobePath()
        if not ffmpegPath or not ffprobePath:
            raise TaskError("{name} 未安装，请在设置中安装", name="FFmpeg")

        Path(self.outputFile).parent.mkdir(parents=True, exist_ok=True)
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

        args.append(self.outputFile)

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

            self.setStatus(TaskStatus.COMPLETED)

            if self.shouldDeleteSource:
                deletePath(inputPath)
                deletePath(Path(f"{inputPath}.ghd"))
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

        Path(self.outputFile).parent.mkdir(parents=True, exist_ok=True)
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

        args.append(self.outputFile)

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

            self.setStatus(TaskStatus.COMPLETED)

            if self.shouldDeleteSource:
                for path in (self._videoPath, self._audioPath):
                    deletePath(path)
                    deletePath(Path(f"{path}.ghd"))
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
        fd, path = tempfile.mkstemp(suffix=".txt", prefix="gd3_chapters_")
        with open(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return path


@dataclass(kw_only=True)
class YouTubeCoverStep(HttpTaskStep):

    @property
    def outputPath(self) -> str:
        stem = Path(self.task.name).stem
        return str(self.task.outputFolder / f"{stem}.jpg")

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        if not self.task.isCoverEnabled:
            self.setStatus(TaskStatus.COMPLETED)
            return
        await super().run(reportSpeed, waitForSpeedLimit)
