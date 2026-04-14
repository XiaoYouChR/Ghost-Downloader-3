import asyncio
import re
import sys
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger
from yt_dlp import YoutubeDL

from app.bases.interfaces import Worker
from app.bases.models import Task, TaskStage, TaskStatus
from app.supports.config import DEFAULT_HEADERS, cfg
from app.supports.utils import getProxies, sanitizeFilename
from .config import ytdlpConfig

try:
    from ffmpeg_pack.config import resolveFFmpegExecutables
except ImportError:
    from features.ffmpeg_pack.config import resolveFFmpegExecutables


_PROGRESS_PATTERN = re.compile(
    r"\[download\]\s+(?P<progress>\d+(?:\.\d+)?)%\s+of\s+(?P<total>[~\d\.\sA-Za-z]+?)(?:\s+at\s+(?P<speed>[~\d\.\sA-Za-z/]+?))?(?:\s+ETA\s+\S+)?$",
    re.IGNORECASE,
)
_SIZE_PATTERN = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>[KMGTPE]?i?B|B)", re.IGNORECASE)
_DESTINATION_PATTERN = re.compile(r"\[download\]\s+Destination:\s+(?P<path>.+)$")
_MERGE_PATTERN = re.compile(r"\[Merger\].*?\"(?P<path>.+)\"")


def _pickProxy(proxies: dict | None) -> str:
    if not isinstance(proxies, dict):
        return ""

    for key in ("https", "http", "all", "ftp"):
        value = proxies.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def _parseSizeToBytes(text: str) -> int:
    match = _SIZE_PATTERN.search((text or "").strip())
    if not match:
        return 0

    value = float(match.group("value"))
    unit = match.group("unit").lower()
    factors = {
        "b": 1,
        "kb": 1000,
        "mb": 1000 ** 2,
        "gb": 1000 ** 3,
        "tb": 1000 ** 4,
        "pb": 1000 ** 5,
        "eb": 1000 ** 6,
        "kib": 1024,
        "mib": 1024 ** 2,
        "gib": 1024 ** 3,
        "tib": 1024 ** 4,
        "pib": 1024 ** 5,
        "eib": 1024 ** 6,
    }
    return int(value * factors.get(unit, 1))


def _resolveOutputExt(info: dict[str, Any]) -> str:
    ext = str(info.get("ext") or "").strip().lower()
    if ext:
        return ext

    downloads = info.get("requested_downloads") or []
    if isinstance(downloads, list):
        for item in downloads:
            if not isinstance(item, dict):
                continue
            extension = str(item.get("ext") or "").strip().lower()
            if extension:
                return extension

    return "mp4"


def _buildFormatSelector(*, mode: str, maxHeight: str, audioFormat: str, videoContainer: str) -> str:
    maxHeight = str(maxHeight or "best").strip().lower()
    videoContainer = str(videoContainer or "mp4").strip().lower()
    heightFilter = ""
    if maxHeight.isdigit():
        heightFilter = f"[height<={maxHeight}]"

    if mode == "audio_only":
        if audioFormat == "best":
            return "bestaudio/b"
        return f"bestaudio[ext={audioFormat}]/bestaudio/b"

    if mode == "best_mp4" and videoContainer == "mp4":
        mp4Video = f"bv*[ext=mp4]{heightFilter}"
        anyVideo = f"bv*{heightFilter}"
        return f"{mp4Video}+ba[ext=m4a]/{mp4Video}+ba/{anyVideo}+ba/b[ext=mp4]/b"

    if mode == "best_mp4" and videoContainer == "webm":
        webmVideo = f"bv*[ext=webm]{heightFilter}"
        anyVideo = f"bv*{heightFilter}"
        return f"{webmVideo}+ba[ext=webm]/{webmVideo}+ba/{anyVideo}+ba/b"

    anyVideo = f"bv*{heightFilter}"
    return f"{anyVideo}+ba/b"


def _predictOutputExt(mode: str, audioFormat: str, videoContainer: str, preferMp4: bool) -> str:
    if mode == "audio_only":
        return audioFormat if audioFormat != "best" else "mp3"
    if str(videoContainer or "").lower() in {"mp4", "webm", "mkv"}:
        return str(videoContainer).lower()
    if preferMp4:
        return "mp4"
    return "webm"


def _estimateSelectedSize(info: dict[str, Any]) -> int:
    total = 0

    requestedFormats = info.get("requested_formats")
    if isinstance(requestedFormats, list) and requestedFormats:
        for item in requestedFormats:
            if not isinstance(item, dict):
                continue
            size = int(item.get("filesize") or item.get("filesize_approx") or 0)
            if size > 0:
                total += size
        if total > 0:
            return total

    requestedDownloads = info.get("requested_downloads")
    if isinstance(requestedDownloads, list) and requestedDownloads:
        for item in requestedDownloads:
            if not isinstance(item, dict):
                continue
            size = int(item.get("filesize") or item.get("filesize_approx") or 0)
            if size > 0:
                total += size
        if total > 0:
            return total

    size = int(info.get("filesize") or info.get("filesize_approx") or 0)
    return size if size > 0 else 0


async def _extractInfo(
    url: str,
    headers: dict[str, str],
    proxies: dict | None,
    *,
    formatSelector: str,
    useCookiesFromBrowser: bool,
    cookiesBrowser: str,
) -> dict[str, Any]:
    def _blockingExtract() -> dict[str, Any]:
        filteredHeaders = {
            str(key): str(value)
            for key, value in headers.items()
            if str(key).strip().lower() != "cookie" and str(value).strip()
        }

        ydlOptions: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": 30,
            "http_headers": filteredHeaders,
            "format": formatSelector,
        }

        if useCookiesFromBrowser:
            ydlOptions["cookiesfrombrowser"] = (cookiesBrowser,)

        proxy = _pickProxy(proxies)
        if proxy:
            ydlOptions["proxy"] = proxy

        with YoutubeDL(ydlOptions) as ydl:
            info = ydl.extract_info(url, download=False)

        if isinstance(info, dict) and isinstance(info.get("entries"), list):
            for entry in info["entries"]:
                if isinstance(entry, dict):
                    return entry

        if not isinstance(info, dict):
            raise ValueError("yt-dlp 返回了无效的视频信息")

        return info

    return await asyncio.to_thread(_blockingExtract)


@dataclass
class YtDlpTaskStage(TaskStage):
    resolvePath: str
    outputTemplate: str
    lastMessage: str = field(default="")


@dataclass
class YtDlpTask(Task):
    headers: dict = field(default_factory=DEFAULT_HEADERS.copy)
    proxies: dict | None = field(default_factory=getProxies)
    outputExt: str = field(default="mp4")
    formatSelector: str = field(default="bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b")
    mode: str = field(default="best_mp4")
    maxHeight: str = field(default="best")
    videoContainer: str = field(default="mp4")
    audioFormat: str = field(default="mp3")
    useCookiesFromBrowser: bool = field(default=False)
    cookiesBrowser: str = field(default="chrome")

    @property
    def outputBaseName(self) -> str:
        suffix = f".{self.outputExt.lower()}"
        if self.title.lower().endswith(suffix):
            return self.title[:-len(suffix)]
        return Path(self.title).stem

    def syncStagePaths(self):
        outputTemplate = str(Path(self.path) / f"{self.outputBaseName}.%(ext)s")
        resolvePath = str(Path(self.path) / self.title)
        for stage in self.stages:
            if isinstance(stage, YtDlpTaskStage):
                stage.outputTemplate = outputTemplate
                stage.resolvePath = resolvePath

    def applyPayloadToTask(self, payload: dict[str, Any]):
        super().applyPayloadToTask(payload)

        headers = payload.get("headers")
        if isinstance(headers, dict):
            self.headers = headers.copy()

        if "proxies" in payload:
            proxies = payload.get("proxies")
            if isinstance(proxies, dict) or proxies is None:
                self.proxies = proxies

        mode = payload.get("ytdlpMode")
        if isinstance(mode, str) and mode in {"best_mp4", "best", "audio_only"}:
            self.mode = mode

        maxHeight = payload.get("ytdlpMaxHeight")
        if isinstance(maxHeight, str):
            self.maxHeight = maxHeight

        audioFormat = payload.get("ytdlpAudioFormat")
        if isinstance(audioFormat, str):
            self.audioFormat = audioFormat

        videoContainer = payload.get("ytdlpVideoContainer")
        if isinstance(videoContainer, str) and videoContainer.lower() in {"mp4", "webm", "mkv"}:
            self.videoContainer = videoContainer.lower()

        useCookiesFromBrowser = payload.get("ytdlpUseCookiesFromBrowser")
        if isinstance(useCookiesFromBrowser, bool):
            self.useCookiesFromBrowser = useCookiesFromBrowser

        cookiesBrowser = payload.get("ytdlpCookiesBrowser")
        if isinstance(cookiesBrowser, str) and cookiesBrowser:
            self.cookiesBrowser = cookiesBrowser

        self.formatSelector = _buildFormatSelector(
            mode=self.mode,
            maxHeight=self.maxHeight,
            audioFormat=self.audioFormat,
            videoContainer=self.videoContainer,
        )

        self.syncStagePaths()

    async def run(self):
        currentStage = None
        try:
            for stage in self.iterRunnableStages():
                currentStage = stage
                if isinstance(stage, YtDlpTaskStage):
                    await YtDlpWorker(stage).run()
                    continue

                raise TypeError(f"不支持的 YtDlpTaskStage: {type(stage).__name__}")
        except asyncio.CancelledError:
            logger.info(f"{self.title} 停止下载")
            raise
        except Exception as e:
            if currentStage is not None and not currentStage.error:
                currentStage.setError(e)
            logger.opt(exception=e).error("{} 下载失败", self.title)
            raise

    def __hash__(self):
        return hash(self.taskId)


class YtDlpWorker(Worker):
    def __init__(self, stage: YtDlpTaskStage):
        super().__init__(stage)
        self.stage = stage
        self.task: YtDlpTask = getattr(stage, "_task")

    def _buildArguments(self) -> list[str]:
        args = [
            "-m",
            "yt_dlp",
            self.task.url,
            "--newline",
            "--ignore-config",
            "--no-warnings",
            "--no-playlist",
            "--progress",
            "--no-colors",
            "--format",
            self.task.formatSelector,
            "--output",
            self.stage.outputTemplate,
        ]

        ffmpegPath, _ = resolveFFmpegExecutables()
        if ffmpegPath:
            args.extend(["--ffmpeg-location", ffmpegPath])

        if self.task.mode != "audio_only":
            args.extend(["--merge-output-format", self.task.videoContainer])

        if self.task.mode == "audio_only":
            args.append("--extract-audio")
            if self.task.audioFormat != "best":
                args.extend(["--audio-format", self.task.audioFormat])
            args.extend(["--audio-quality", "0"])

        if self.task.useCookiesFromBrowser:
            args.extend(["--cookies-from-browser", self.task.cookiesBrowser])

        proxy = _pickProxy(self.task.proxies)
        if proxy:
            args.extend(["--proxy", proxy])

        for name, value in self.task.headers.items():
            if str(name).strip().lower() == "cookie":
                continue
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            args.extend(["--add-header", f"{name}: {text}"])

        return args

    def _resolveFinalOutput(self) -> Path | None:
        baseName = self.task.outputBaseName.lower()
        outputDir = Path(self.task.path)
        if not outputDir.is_dir():
            return None

        candidates: list[Path] = []
        ignoredSuffixes = {".part", ".ytdl", ".tmp"}
        for item in outputDir.iterdir():
            if not item.is_file():
                continue
            if item.suffix.lower() in ignoredSuffixes:
                continue
            if not item.stem.lower().startswith(baseName):
                continue
            candidates.append(item)

        if not candidates:
            return None

        candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return candidates[0]

    def _syncFinalOutput(self):
        candidate = self._resolveFinalOutput()
        if candidate is None:
            return

        self.task.outputExt = candidate.suffix.lstrip(".") or self.task.outputExt
        self.task.fileSize = max(self.task.fileSize, candidate.stat().st_size)
        if candidate.name != self.task.title:
            self.task.setTitle(candidate.name)

    def _handleOutputLine(self, line: str):
        text = line.strip()
        if not text:
            return

        self.stage.lastMessage = text[:1000]

        destinationMatch = _DESTINATION_PATTERN.search(text)
        if destinationMatch:
            destination = destinationMatch.group("path").strip().strip('"')
            if destination:
                finalPath = Path(destination)
                self.stage.resolvePath = str(finalPath)
            return

        mergeMatch = _MERGE_PATTERN.search(text)
        if mergeMatch:
            merged = mergeMatch.group("path").strip()
            if merged:
                self.stage.resolvePath = merged
            return

        progressMatch = _PROGRESS_PATTERN.search(text)
        if not progressMatch:
            return

        progress = float(progressMatch.group("progress"))
        totalSize = _parseSizeToBytes(progressMatch.group("total"))
        speed = _parseSizeToBytes(progressMatch.group("speed") or "")

        self.stage.progress = progress
        if totalSize > 0:
            self.task.fileSize = totalSize
            self.stage.receivedBytes = int((progress / 100.0) * totalSize)
        self.stage.speed = speed

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
        Path(self.task.path).mkdir(parents=True, exist_ok=True)

        process = None
        outputTask = None

        try:
            args = self._buildArguments()
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                *args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            outputTask = asyncio.create_task(self._readOutput(process.stdout))

            await process.wait()
            if outputTask is not None:
                await outputTask

            if process.returncode != 0:
                message = self.stage.lastMessage or f"yt-dlp 退出码异常: {process.returncode}"
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


async def parse(payload: dict) -> YtDlpTask:
    url = str(payload["url"]).strip()
    headers = payload.get("headers", DEFAULT_HEADERS)
    proxies = payload.get("proxies", getProxies())
    path = Path(payload.get("path", cfg.downloadFolder.value))

    requestHeaders = headers.copy() if isinstance(headers, dict) else DEFAULT_HEADERS.copy()
    mode = str(payload.get("ytdlpMode", ytdlpConfig.mode.value))
    maxHeight = str(payload.get("ytdlpMaxHeight", ytdlpConfig.maxHeight.value))
    videoContainer = str(payload.get("ytdlpVideoContainer", ytdlpConfig.videoContainer.value)).lower()
    audioFormat = str(payload.get("ytdlpAudioFormat", ytdlpConfig.audioFormat.value))
    useCookiesFromBrowser = bool(payload.get("ytdlpUseCookiesFromBrowser", ytdlpConfig.useCookiesFromBrowser.value))
    cookiesBrowser = str(payload.get("ytdlpCookiesBrowser", ytdlpConfig.cookiesBrowser.value))

    formatSelector = _buildFormatSelector(
        mode=mode,
        maxHeight=maxHeight,
        audioFormat=audioFormat,
        videoContainer=videoContainer,
    )
    info = await _extractInfo(
        url,
        requestHeaders,
        proxies,
        formatSelector=formatSelector,
        useCookiesFromBrowser=useCookiesFromBrowser,
        cookiesBrowser=cookiesBrowser,
    )

    rawTitle = str(info.get("title") or "").strip()
    extractor = str(info.get("extractor") or "").strip().lower()
    ext = _predictOutputExt(
        mode=mode,
        audioFormat=audioFormat,
        videoContainer=videoContainer,
        preferMp4=(mode == "best_mp4"),
    )
    if mode == "best":
        ext = _resolveOutputExt(info)
    fallbackTitle = extractor or "video"
    title = f"{sanitizeFilename(rawTitle, fallback=fallbackTitle)}.{ext}"

    fileSize = _estimateSelectedSize(info)
    if fileSize <= 0:
        fileSize = 1

    task = YtDlpTask(
        title=title,
        url=url,
        fileSize=fileSize,
        headers=requestHeaders,
        proxies=proxies,
        path=path,
        outputExt=ext,
        mode=mode,
        maxHeight=maxHeight,
        videoContainer=videoContainer,
        audioFormat=audioFormat,
        useCookiesFromBrowser=useCookiesFromBrowser,
        cookiesBrowser=cookiesBrowser,
        formatSelector=formatSelector,
    )
    task.addStage(
        YtDlpTaskStage(
            stageIndex=1,
            resolvePath="",
            outputTemplate="",
        )
    )
    task.syncStagePaths()
    return task
