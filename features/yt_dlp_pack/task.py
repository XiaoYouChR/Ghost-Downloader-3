from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from app.models.task import Task, TaskError, TaskStep, TaskStatus
from app.platform.filesystem import toPosixPath
from .config import ytDlpConfig, ytDlpRuntime

DEFAULT_VIDEO_FORMAT = "bv*+ba/b"
PROGRESS_TOKEN = "__GD3_PROGRESS__"
FINAL_FILE_TOKEN = "__GD3_FINAL__"
PROGRESS_TEMPLATE = (
    f"download:{PROGRESS_TOKEN}"
    "%(progress.downloaded_bytes)s|%(progress.total_bytes)s|"
    "%(progress.total_bytes_estimate)s|%(progress.speed)s"
)
FINAL_TEMPLATE = f"after_move:{FINAL_FILE_TOKEN}%(filepath)s"

ERROR_HINTS = (
    ("is not available in your country", "Video not available in your region, try configuring a proxy"),
    ("video unavailable", "Video unavailable (may be deleted or private)"),
    ("private video", "Private video, requires cookies from an authorized account"),
    ("members-only", "Members-only video, requires cookies from a member account"),
    ("confirm your age", "Age-restricted video, requires cookies from a logged-in account"),
    ("confirm you're not a bot", "YouTube requires human verification, configure cookies in settings"),
    ("requested format is not available", "Requested format not available, try a different quality"),
    ("http error 403", "Download rejected (403), link may have expired"),
)


def toInt(value: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


@dataclass(kw_only=True, eq=False)
class YtDlpTask(Task):
    packId: str = "ytdlp"
    canEdit = True
    videoFormat: str = DEFAULT_VIDEO_FORMAT
    subtitleLanguages: str = ""
    shouldIncludeAutoSubs: bool = False
    isPlaylist: bool = False
    videos: list[dict] = field(default_factory=list)

    def currentSnapshot(self) -> tuple[float, int, int]:
        if not self.steps or len(self.steps) == 1:
            return super().currentSnapshot()
        completedCount = sum(1 for s in self.steps if s.status == TaskStatus.COMPLETED)
        currentStep = next((s for s in self.steps if s.status == TaskStatus.RUNNING), None)
        totalCount = len(self.steps)
        if currentStep:
            progress = (completedCount * 100 + currentStep.progress) / totalCount
            speed = currentStep.speed
        else:
            progress = completedCount * 100 / totalCount
            speed = 0
        receivedBytes = sum(s.receivedBytes for s in self.steps)
        return progress, speed, receivedBytes

    def setVideos(self, videos: list[dict]) -> None:
        self.videos = videos
        self._rebuildSteps()

    def setSelectedVideos(self, indices: set[int]) -> None:
        for i, video in enumerate(self.videos):
            video["selected"] = i in indices
        self._rebuildSteps()

    def _rebuildSteps(self) -> None:
        self._savedHeaders = self.steps[0].headers if self.steps else getattr(self, "_savedHeaders", {})
        self.steps.clear()
        if not self.videos:
            self.addStep(YtDlpTaskStep(stepIndex=1, headers=self._savedHeaders))
            return
        for video in self.videos:
            if not video.get("selected", True):
                continue
            self.addStep(YtDlpTaskStep(
                stepIndex=len(self.steps) + 1,
                videoUrl=f"https://www.youtube.com/watch?v={video['id']}",
                videoTitle=str(video.get("title") or ""),
                headers=self._savedHeaders,
            ))
        if not self.steps:
            self.addStep(YtDlpTaskStep(stepIndex=1, headers=self._savedHeaders))


@dataclass(kw_only=True)
class YtDlpTaskStep(TaskStep):
    videoUrl: str = ""
    videoTitle: str = ""
    outputFile: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    lastMessage: str = ""

    @property
    def _outputTemplate(self) -> str:
        return toPosixPath(self.task.outputFolder / "%(title)s.%(ext)s")

    def _buildCommand(self) -> list[str]:
        from ffmpeg_pack.config import ffmpegRuntime

        url = self.videoUrl or self.task.url
        task: YtDlpTask = self.task
        args = [
            url,
            "-f", task.videoFormat,
            "-o", self._outputTemplate,
            "--no-playlist",
            "--newline",
            "--no-color",
            "--no-simulate",
            "--progress",
            "--progress-template", PROGRESS_TEMPLATE,
            "--print", FINAL_TEMPLATE,
        ]

        if ytDlpConfig.shouldPreferMp4.value:
            args.extend(["--format-sort", "ext:mp4:m4a"])

        ffmpegPath = ffmpegRuntime.path()
        if ffmpegPath:
            args.extend(["--ffmpeg-location", ffmpegPath])

        from app.config.cfg import cfg, proxy
        proxyUrl = proxy()
        if proxyUrl:
            args.extend(["--proxy", proxyUrl])
        if cfg.isSpeedLimitEnabled.value:
            args.extend(["--limit-rate", str(cfg.speedLimitation.value)])

        fragments = ytDlpConfig.parallelFragments.value
        if fragments > 1:
            args.extend(["--concurrent-fragments", str(fragments)])

        browser = ytDlpConfig.loginBrowser.value
        if browser:
            args.extend(["--cookies-from-browser", browser])

        if task.subtitleLanguages:
            args.extend(["--write-subs", "--sub-langs", task.subtitleLanguages])
            if task.shouldIncludeAutoSubs:
                args.append("--write-auto-subs")

        if ytDlpConfig.shouldEmbedThumbnail.value:
            # Convert to jpg so embedding never needs FFmpeg's png/zlib path — our
            # minimal FFmpeg ships mjpeg only (webp/jpg thumbnails, no png).
            args.extend(["--embed-thumbnail", "--convert-thumbnails", "jpg"])
        if ytDlpConfig.shouldEmbedChapters.value:
            args.append("--embed-chapters")
        if ytDlpConfig.shouldEmbedMetadata.value:
            args.append("--embed-metadata")

        for name, value in self.headers.items():
            text = value.strip()
            if text:
                args.extend(["--add-header", f"{name}:{text}"])

        return args

    def _parseOutputLine(self, line: str) -> None:
        text = line.strip()
        if not text:
            return
        if text.startswith(FINAL_FILE_TOKEN):
            self._finalPath = text[len(FINAL_FILE_TOKEN):].strip()
            return
        if text.startswith(PROGRESS_TOKEN):
            parts = text[len(PROGRESS_TOKEN):].split("|")
            if len(parts) >= 4:
                downloaded = toInt(parts[0])
                total = toInt(parts[1]) or toInt(parts[2])
                self.speed = toInt(parts[3])
                self.receivedBytes = self._completedBytes + downloaded
                if total > 0:
                    if self._totalBytes > 0 and total != self._totalBytes:
                        self._completedBytes += self._totalBytes
                        self.receivedBytes += self._totalBytes
                    self._totalBytes = total
                    allTotal = self._completedBytes + total
                    if len(self.task.steps) == 1:
                        self.task.fileSize = max(self.task.fileSize, allTotal)
                    self.progress = min(99.5, self.receivedBytes / allTotal * 100)
            return
        self.lastMessage = text[:1000]

    async def _readOutput(self, stream: asyncio.StreamReader) -> None:
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
                self._parseOutputLine(line)
        if buffer.strip():
            self._parseOutputLine(buffer)

    async def run(self) -> None:
        execPath = ytDlpRuntime.path()
        if not execPath:
            raise TaskError("Binary not found: {name}", name="yt-dlp")

        self._finalPath = ""
        self._totalBytes = 0
        self._completedBytes = 0
        self.task.outputFolder.mkdir(parents=True, exist_ok=True)

        process = await asyncio.create_subprocess_exec(
            execPath,
            *self._buildCommand(),
            cwd=Path(execPath).parent,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        readerTask = asyncio.create_task(self._readOutput(process.stdout))

        try:
            await process.wait()
            await readerTask

            if process.returncode != 0:
                lowered = self.lastMessage.lower()
                hint = next((h for needle, h in ERROR_HINTS if needle in lowered), "")
                raise TaskError(
                    hint or "Process exited with error ({code}): {detail}",
                    code=process.returncode,
                    detail=self.lastMessage or "yt-dlp",
                )

            if self._finalPath:
                self.outputFile = self._finalPath
                path = Path(self._finalPath)
                if path.is_file() and path.stat().st_size > 0:
                    if len(self.task.steps) == 1:
                        self.task.fileSize = max(self.task.fileSize, path.stat().st_size)
                        if path.name != self.task.name:
                            self.task.setName(path.name)

            self.setStatus(TaskStatus.COMPLETED)
        except asyncio.CancelledError:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=3)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
            if not readerTask.done():
                readerTask.cancel()
                with suppress(asyncio.CancelledError):
                    await readerTask
            self.setStatus(TaskStatus.PAUSED)
            raise
