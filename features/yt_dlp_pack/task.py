from __future__ import annotations

import asyncio
import importlib
import re
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

ERROR_HINTS = (
    ("is not available in your country", "该视频在您所在地区不可用，请尝试配置代理（{detail}）"),
    ("video unavailable", "视频不可用，可能已被删除或设为私密（{detail}）"),
    ("private video", "私密视频，需要已授权账号的 Cookie（{detail}）"),
    ("members-only", "会员专属视频，需要会员账号的 Cookie（{detail}）"),
    ("confirm your age", "年龄限制视频，需要已登录账号的 Cookie（{detail}）"),
    ("confirm you're not a bot", "YouTube 需要人机验证，请在设置中配置 Cookie（{detail}）"),
    ("requested format is not available", "请求的格式不可用，请稍后重试（{detail}）"),
    ("http error 403", "下载被拒绝（403），链接可能已失效（{detail}）"),
    ("decrypt", "浏览器 Cookie 解密失败，请在设置中手动导入 Cookie 或使用浏览器扩展（{detail}）"),
    ("could not copy", "无法读取浏览器 Cookie 数据库，请关闭浏览器后重试或手动导入 Cookie（{detail}）"),
)

STEPS_PER_VIDEO = 4

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
    from .config import cookieFile, hasCookieFile, youTubeRuntime, ytDlpConfig
    from app.config.cfg import proxy

    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "allowed_extractors": ["youtube.*"],
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
        opts["cookiefile"] = str(cookieFile())
    else:
        browser = ytDlpConfig.loginBrowser.value
        if browser:
            opts["cookiesfrombrowser"] = (browser,)
    return opts


def probeFormats(url: str) -> dict:
    loadYtDlpToPath()
    yt_dlp = importlib.import_module("yt_dlp")
    opts = buildYtDlpOptions()
    hasCookie = "cookiefile" in opts or "cookiesfrombrowser" in opts
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception:
        if not hasCookie:
            raise
        logger.info("retrying without cookies for {}", url)
        opts.pop("cookiefile", None)
        opts.pop("cookiesfrombrowser", None)
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


@dataclass(kw_only=True)
class YouTubeFile(TaskFile):
    videoId: str = ""
    duration: int = 0


def buildStepGroup(fileIndex: int, videoUrl: str = "", videoStem: str = "") -> list[TaskStep]:
    base = fileIndex * STEPS_PER_VIDEO
    return [
        YouTubeExtractStep(stepIndex=base + 1, fileIndex=fileIndex, videoUrl=videoUrl),
        YouTubeResourceStep(stepIndex=base + 2, fileIndex=fileIndex, videoStem=videoStem, role="video"),
        YouTubeResourceStep(stepIndex=base + 3, fileIndex=fileIndex, videoStem=videoStem, role="audio"),
        YouTubeMergeStep(stepIndex=base + 4, fileIndex=fileIndex, videoStem=videoStem),
    ]


@dataclass(kw_only=True, eq=False)
class YouTubeTask(Task):
    packId: str = "ytdlp"
    canEdit = True
    fileType = YouTubeFile
    videoFormatFilter: str = ""
    subtitleLanguages: str = ""
    shouldIncludeAutoSubs: bool = False
    isPlaylist: bool = False

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

    async def run(self) -> None:
        if self._hasFreshSiblingUrls():
            self.setStatus(TaskStatus.COMPLETED)
            return

        from .config import youTubeRuntime
        if not youTubeRuntime.path():
            raise TaskError("{name} 未安装，请在设置中安装", name="YouTube 运行环境")

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

        videoFmt, audioFmt = self._buildFormatPair(info)
        if not videoFmt and not audioFmt:
            logger.warning("no formats found for {} (formats count: {})", url, len(info.get("formats") or []))
            raise TaskError("未找到可用的视频格式")

        self._updateSiblingSteps(videoFmt, audioFmt, info)
        logger.info("selected video={} audio={} for {}",
                     videoFmt.get("format_id") if videoFmt else None,
                     audioFmt.get("format_id") if audioFmt else None, url)

        title = info.get("title")
        if title:
            from app.platform.filesystem import toSafeFilename
            safeName = toSafeFilename(title)
            if safeName:
                if self.fileIndex == 0 and not self.task.isPlaylist:
                    ext = "m4a" if not videoFmt else "mp4"
                    self.task.setName(f"{safeName}.{ext}")
                for step in self.task.steps:
                    if getattr(step, "fileIndex", -1) == self.fileIndex and hasattr(step, "videoStem"):
                        step.videoStem = safeName

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

    def _buildFormatPair(self, info: dict) -> tuple[dict | None, dict | None]:
        from .config import ytDlpConfig
        formats = info.get("formats") or []
        shouldPreferMp4 = ytDlpConfig.shouldPreferMp4.value
        filterStr = self.task.videoFormatFilter
        isAudioOnly = filterStr and "bv" not in filterStr

        audioFormats = [
            f for f in formats
            if f.get("acodec", "none") != "none"
            and f.get("vcodec", "none") == "none"
        ]

        audioFormats.sort(
            key=lambda f: (shouldPreferMp4 and f.get("ext") in ("mp4", "m4a"), f.get("abr") or f.get("tbr") or 0),
            reverse=True,
        )
        audioFmt = audioFormats[0] if audioFormats else None

        if isAudioOnly:
            return None, audioFmt

        videoFormats = [
            f for f in formats
            if f.get("vcodec", "none") != "none"
            and f.get("acodec", "none") == "none"
        ]

        heightMatch = re.search(r"height<=(\d+)", filterStr) if filterStr else None
        if heightMatch:
            maxHeight = int(heightMatch.group(1))
            videoFormats = [f for f in videoFormats if (f.get("height") or 0) <= maxHeight]

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

    def _updateSiblingSteps(self, videoFmt: dict | None, audioFmt: dict | None, info: dict) -> None:
        from app.config.cfg import cfg
        from .config import ytDlpConfig

        for step in self.task.steps:
            if getattr(step, "fileIndex", -1) != self.fileIndex:
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

    async def run(self) -> None:
        if not self.url:
            self.setStatus(TaskStatus.COMPLETED)
            return
        await super().run()


@dataclass(kw_only=True)
class YouTubeMergeStep(FFmpegStep):
    fileIndex: int = 0
    videoStem: str = ""
    metadataTitle: str = ""
    metadataArtist: str = ""
    chapters: list[dict] = field(default_factory=list)

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

    async def run(self) -> None:
        hasVideo = self._videoPath.exists()
        hasAudio = self._audioPath.exists()

        if hasVideo and hasAudio:
            if self.metadataTitle or self.chapters:
                await self._runWithMetadata()
            else:
                await super().run()
            return

        singleInput = self._videoPath if hasVideo else self._audioPath if hasAudio else None
        if singleInput:
            outputPath = Path(self.outputFile)
            outputPath.parent.mkdir(parents=True, exist_ok=True)

            # Check if the user wants audio transcoding (only applies to audio-only downloads)
            from .config import ytDlpConfig
            targetFmt = ytDlpConfig.audioOutputFormat.value
            if not hasVideo and targetFmt and targetFmt != "original":
                # Transcode directly from singleInput (no rawAudio temp file)
                await self._transcodeAudio(str(singleInput), targetFmt, str(outputPath.parent))
                # Delete the downloaded raw audio files only after successful transcoding
                singleInput.unlink(missing_ok=True)
                Path(f"{singleInput}.ghd").unlink(missing_ok=True)
            else:
                shutil.move(str(singleInput), str(outputPath))
                Path(f"{singleInput}.ghd").unlink(missing_ok=True)

        self.setStatus(TaskStatus.COMPLETED)

    async def _transcodeAudio(self, inputPath: str, targetFormat: str, outputFolder: str) -> None:
        """Transcode an audio file to *targetFormat* using FFmpeg."""
        from ffmpeg_pack.config import ffmpegRuntime

        ffmpegPath = ffmpegRuntime.path()
        if not ffmpegPath:
            raise TaskError("{name} 未安装，请在设置中安装", name="FFmpeg")

        stem = Path(inputPath).stem
        # Strip internal suffixes to get clean final output filename
        if stem.endswith(".audio"):
            stem = stem[:-6]
        elif stem.endswith(".raw"):
            stem = stem[:-4]
        outputFile = str(Path(outputFolder) / f"{stem}.{targetFormat}")


        # Build codec args per format
        match targetFormat:
            case "mp3":
                codec_args = ["-codec:a", "libmp3lame", "-q:a", "2"]
            case "wav":
                codec_args = ["-codec:a", "pcm_s16le"]
            case "flac":
                codec_args = ["-codec:a", "flac"]
            case "opus":
                codec_args = ["-codec:a", "libopus", "-b:a", "128k"]
            case _:
                codec_args = []

        args = [
            ffmpegPath,
            "-y", "-v", "error", "-nostats", "-progress", "pipe:1",
            "-i", inputPath,
            *codec_args,
            outputFile,
        ]

        ffprobePath = ffmpegRuntime.ffprobePath()
        totalDuration = await self._probeDuration(ffprobePath, Path(inputPath)) if ffprobePath else 0

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
                    "FFmpeg 转码失败（{code}）：{detail}",
                    code=process.returncode,
                    detail=stderr or "unknown error",
                )

            # Update the task name to reflect the transcoded format
            self.task.setName(f"{stem}.{targetFormat}")
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


    async def _runWithMetadata(self) -> None:
        from ffmpeg_pack.config import ffmpegRuntime
        from app.platform.filesystem import deletePath

        ffmpegPath = ffmpegRuntime.path()
        ffprobePath = ffmpegRuntime.ffprobePath()
        if not ffmpegPath or not ffprobePath:
            raise TaskError("{name} 未安装，请在设置中安装", name="FFmpeg")

        Path(self.outputFile).parent.mkdir(parents=True, exist_ok=True)
        totalDuration = await self._probeDuration(ffprobePath, self._videoPath)

        args = [
            ffmpegPath,
            "-y", "-v", "error", "-nostats", "-progress", "pipe:1",
            "-i", str(self._videoPath),
            "-i", str(self._audioPath),
        ]

        chaptersFile = None
        if self.chapters:
            chaptersFile = self._createChaptersFile()
            args.extend(["-f", "ffmetadata", "-i", chaptersFile])

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
