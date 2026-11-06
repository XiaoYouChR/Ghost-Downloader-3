from __future__ import annotations

import asyncio
import re
import shutil
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from loguru import logger

from app.client import buildClient, toEmulation
from app.config.cfg import cfg
from app.models.task import Task, TaskError, TaskStatus, TaskStep
from app.platform.filesystem import deletePath, splitStemExt, toSafeFilename
from http_pack.task import HttpTaskStep, matchRange
from .config import ffmpegRuntime
from .container import (
    ContainerIndex,
    buildSegmentRange,
    buildTimeSuffix,
    findMoovRange,
    parseContainerIndex,
)

HEAD_PROBE_SIZE = 64 << 10
ISOBMFF_BOX_TYPES = {b"ftyp", b"styp", b"moof", b"moov", b"free", b"skip", b"mdat", b"pdin"}
FORMAT_BY_EXT = {
    ".mp4": "mp4",
    ".m4v": "mp4",
    ".mov": "mov",
    ".webm": "webm",
    ".mkv": "matroska",
    ".m4a": "ipod",
}
TIME_SUFFIX_RE = re.compile(r"\s*\[\d{2,}m\d{2}s-\d{2,}m\d{2}s\]$")


def toResourcePath(task: Task, role: str, extension: str) -> Path:
    return task.partPath / (f"{role}.{extension}" if extension else role)


async def fetchRange(
    url: str,
    offset: int,
    length: int,
    *,
    headers: dict[str, str] | None = None,
    clientProfile: str = "",
    userAgent: str = "",
    sourceUserAgent: str = "",
    requireExactLength: bool = True,
) -> bytes:
    emulation = toEmulation(clientProfile or cfg.clientProfile.value, sourceUserAgent)
    client = buildClient(emulation=emulation, userAgent=userAgent or None, timeout=30)
    try:
        end = offset + length - 1
        reqHeaders = {**(headers or {}), "range": f"bytes={offset}-{end}", "accept-encoding": "identity"}
        response = await client.get(url, headers=reqHeaders)
        try:
            status = response.status.as_int()
            contentRange = bytes(response.headers.get("content-range") or b"")
            if status != 206 or not matchRange(contentRange, offset, end, None):
                raise TaskError("服务器拒绝了范围请求，状态码：{status}", status=status)
            data = bytes(await response.bytes())
        finally:
            response.close()
    finally:
        client.close()
    if not data or (requireExactLength and len(data) != length) or len(data) > length:
        raise TaskError("服务器返回的数据不完整")
    return data


async def probeContainerIndex(
    url: str,
    fileSize: int = 0,
    *,
    probeSize: int = HEAD_PROBE_SIZE,
    headers: dict[str, str] | None = None,
    clientProfile: str = "",
    userAgent: str = "",
    sourceUserAgent: str = "",
) -> tuple[bytes, ContainerIndex] | None:
    hasKnownSize = fileSize > 0
    firstLen = min(fileSize, probeSize) if hasKnownSize else probeSize
    if firstLen <= 0:
        return None
    headerData = await fetchRange(
        url, 0, firstLen,
        headers=headers,
        clientProfile=clientProfile,
        userAgent=userAgent,
        sourceUserAgent=sourceUserAgent,
        requireExactLength=hasKnownSize,
    )
    for _ in range(3):
        moovRange = findMoovRange(headerData, fileSize)
        if moovRange is None:
            break
        prefix, offset, length = moovRange
        if length <= 0:
            break
        extra = await fetchRange(
            url, offset, length,
            headers=headers,
            clientProfile=clientProfile,
            userAgent=userAgent,
            sourceUserAgent=sourceUserAgent,
            requireExactLength=hasKnownSize,
        )
        headerData = prefix + extra
    index = parseContainerIndex(headerData)
    if index is None or index.duration <= 0:
        return None
    return headerData, index


@dataclass(kw_only=True)
class FFmpegResourceStep(HttpTaskStep):
    role: str = ""
    extension: str = ""
    rawFileSize: int = 0
    segStartTime: float = 0.0
    probeEndByte: int = field(default=0, repr=False)
    startTime: float = field(default=0, repr=False)
    endTime: float = field(default=0, repr=False)
    headerData: bytes = field(default=b"", repr=False)
    containerIndex: ContainerIndex | None = field(default=None, repr=False)
    _patchedHeader: bytes = field(default=b"", init=False, repr=False)

    @property
    def outputPath(self) -> str:
        if isinstance(self.task, FFmpegTask) and not self.task.hasAudio and not self.task.isTrimmed:
            return self.task.outputPath
        return str(toResourcePath(self.task, self.role, self.extension))

    async def updateSegmentRange(self) -> None:
        if self.startTime <= 0 and self.endTime <= 0:
            self.httpByteOffset = 0
            self.segStartTime = 0.0
            self._patchedHeader = b""
            if self.rawFileSize > 0:
                self.fileSize = self.rawFileSize
            return

        if not self.headerData or self.containerIndex is None:
            probeSize = max(HEAD_PROBE_SIZE, self.probeEndByte + 1)
            try:
                probed = await probeContainerIndex(
                    self.url,
                    self.rawFileSize,
                    probeSize=probeSize,
                    headers=self.headers,
                    clientProfile=self.clientProfile,
                    userAgent=self.userAgent,
                )
            except TaskError:
                raise
            except Exception as e:
                logger.warning("segment range probe failed for {}: {}", self.url, e)
                probed = None
            if probed is not None:
                self.headerData, self.containerIndex = probed

        if self.headerData and self.containerIndex is not None:
            segRange = buildSegmentRange(
                self.headerData, self.containerIndex, self.startTime, self.endTime,
            )
            if segRange is not None:
                self.httpByteOffset = segRange.segStart
                self.fileSize = segRange.segEnd - segRange.segStart
                self.segStartTime = segRange.segStartTime
                self._patchedHeader = segRange.patchedHeader
                return

        raise TaskError("无法解析媒体索引，无法截取片段")

    async def run(
        self,
        reportSpeed: Callable[[int], None],
        waitForSpeedLimit: Callable[[], Awaitable[None]],
    ) -> None:
        if self.startTime > 0 or self.endTime > 0:
            if not self._patchedHeader:
                await self.updateSegmentRange()
        else:
            self.httpByteOffset = 0
            self.segStartTime = 0.0
            self._patchedHeader = b""
            if self.rawFileSize > 0:
                self.fileSize = self.rawFileSize

        await super().run(reportSpeed, waitForSpeedLimit)

        if self._patchedHeader:
            path = Path(self.outputPath)
            if path.exists():
                tmp = path.with_suffix(f"{path.suffix}.tmp")
                with open(tmp, "wb") as f:
                    f.write(self._patchedHeader)
                    with open(path, "rb") as seg:
                        shutil.copyfileobj(seg, f)
                tmp.replace(path)
            self._patchedHeader = b""


@dataclass(kw_only=True)
class FFmpegStep(TaskStep):
    canPause = False

    videoExtension: str = ""
    audioExtension: str = ""
    shouldDeleteSource: bool = True
    startTime: float = field(default=0, repr=False)
    endTime: float = field(default=0, repr=False)

    @property
    def outputPath(self) -> str:
        return self.task.outputPath

    @property
    def _videoPath(self) -> Path:
        return toResourcePath(self.task, "video", self.videoExtension)

    @property
    def _audioPath(self) -> Path:
        return toResourcePath(self.task, "audio", self.audioExtension)

    @property
    def _timeRange(self) -> tuple[float, float] | None:
        if self.startTime > 0 or self.endTime > 0:
            return self.startTime, self.endTime
        return None

    def _stepForSource(self, source: Path) -> FFmpegResourceStep | None:
        sourceStr = str(source)
        for step in self.task.steps:
            if isinstance(step, FFmpegResourceStep) and step.outputPath == sourceStr:
                return step
        return None

    def _buildTrimArgs(self, source: Path | None = None) -> tuple[list[str], list[str]]:
        tr = self._timeRange
        if not tr:
            return [], []
        step = self._stepForSource(source) if source is not None else None
        if step is None:
            step = next(
                (s for s in self.task.steps
                 if isinstance(s, FFmpegResourceStep) and s.fileIndex == self.fileIndex),
                None,
            )
        segStartTime = step.segStartTime if step is not None else 0.0
        relSS = max(0.0, tr[0] - segStartTime)
        duration = tr[1] - tr[0]
        postArgs = ["-t", str(duration)] if duration > 0 else []
        return ["-ss", str(relSS)], postArgs

    async def run(
        self,
        reportSpeed: Callable[[int], None],
        waitForSpeedLimit: Callable[[], Awaitable[None]],
    ) -> None:
        sources = [p for p in (self._videoPath, self._audioPath) if p.exists()]
        if not sources:
            return
        outputArgs: list[str] = []
        if self._timeRange:
            _, postArgs = self._buildTrimArgs(sources[0])
            ext = Path(self.outputPath).suffix.lower()
            fmt = FORMAT_BY_EXT.get(ext, "mp4")
            outputArgs = [*postArgs, "-f", fmt]
        await self._runMerge(sources, outputArgs=outputArgs)

    async def _runMerge(
        self,
        sources: list[Path],
        *,
        sourceArgs: Sequence[str] = (),
        extraInputArgs: Sequence[str] = (),
        outputArgs: Sequence[str] = (),
    ) -> None:
        ffmpegPath = ffmpegRuntime.path()
        ffprobePath = ffmpegRuntime.ffprobePath()
        if not ffmpegPath or not ffprobePath:
            raise TaskError("{name} 未安装，请在设置中安装", name="FFmpeg")

        tr = self._timeRange
        if tr and tr[1] > tr[0]:
            totalDuration = float(tr[1] - tr[0])
        else:
            totalDuration = await self._probeDuration(ffprobePath, sources[0])

        args = [ffmpegPath, "-y", "-v", "error", "-nostats", "-progress", "pipe:1"]
        for source in sources:
            if sourceArgs:
                perSourceArgs = self._buildTrimArgs(source)[0] if tr else list(sourceArgs)
            elif tr:
                perSourceArgs = self._buildTrimArgs(source)[0]
            else:
                perSourceArgs = []
            args.extend([*perSourceArgs, "-i", str(source)])
        args.extend([*extraInputArgs, "-c", "copy", "-strict", "unofficial", *outputArgs, self.outputPath])

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
                for source in sources:
                    if source.exists():
                        with open(source, "rb") as f:
                            header = f.read(8)
                        isValidMedia = len(header) >= 8 and (
                            header[:4] == b"\x1a\x45\xdf\xa3" or header[4:8] in ISOBMFF_BOX_TYPES
                        )
                        if not isValidMedia:
                            raise TaskError(
                                "文件不是有效的媒体格式，可能受 DRM 保护或下载不完整：{name}",
                                name=source.name,
                            )
                raise TaskError(
                    "FFmpeg 合并失败（{code}）：{detail}",
                    code=process.returncode,
                    detail=stderr or "unknown error",
                )

            if self.shouldDeleteSource:
                for source in sources:
                    deletePath(source)
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

    async def _readProgress(self, stream: asyncio.StreamReader, totalDuration: float) -> None:
        while True:
            rawLine = await stream.readline()
            if not rawLine:
                break
            line = rawLine.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            if line.startswith("out_time_us=") and totalDuration > 0:
                try:
                    currentSeconds = max(0.0, float(line.removeprefix("out_time_us="))) / 1_000_000
                except ValueError:
                    continue
                if currentSeconds > 0:
                    self.progress = min(99.5, max(0.0, currentSeconds / totalDuration * 100))
            elif line == "progress=end":
                self.progress = 100

    async def _probeDuration(self, ffprobePath: str, videoPath: Path) -> float:
        process = await asyncio.create_subprocess_exec(
            ffprobePath,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(videoPath),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        if process.returncode != 0:
            logger.warning("ffprobe 获取时长失败: {}", videoPath)
            return 0.0
        try:
            return max(0.0, float(stdout.decode("utf-8", errors="ignore").strip()))
        except ValueError:
            return 0.0


@dataclass(kw_only=True, eq=False)
class FFmpegTask(Task):
    packId: str = "ffmpeg"
    canEdit = True
    duration: int = 0
    startTime: int = 0
    endTime: int = 0
    baseName: str = ""
    rawFileSize: int = 0
    videoData: bytes = field(default=b"", repr=False)
    videoIndex: ContainerIndex | None = field(default=None, repr=False)
    audioData: bytes = field(default=b"", repr=False)
    audioIndex: ContainerIndex | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.baseName:
            stem, ext = splitStemExt(self.name)
            cleanStem = TIME_SUFFIX_RE.sub("", stem)
            self.baseName = toSafeFilename(f"{cleanStem}{ext}", fallback=self.name)
        if self.rawFileSize <= 0 and self.fileSize > 0 and not self.isTrimmed:
            self.rawFileSize = self.fileSize
        self._syncSteps()
        self.updateStatus()

    @property
    def videoStep(self) -> FFmpegResourceStep:
        return cast(FFmpegResourceStep, self.steps[0])

    @property
    def audioStep(self) -> FFmpegResourceStep | None:
        return next(
            (s for s in self.steps if isinstance(s, FFmpegResourceStep) and s.role == "audio"),
            None,
        )

    @property
    def ffmpegStep(self) -> FFmpegStep:
        return cast(FFmpegStep, self.steps[-1])

    @property
    def hasAudio(self) -> bool:
        return self.audioStep is not None

    @property
    def canTrim(self) -> bool:
        return self.duration > 0

    @property
    def isTrimmed(self) -> bool:
        return self.startTime > 0 or self.endTime > 0

    def isStepSelected(self, step: TaskStep, selectedIndexes: set[int]) -> bool:
        if isinstance(step, FFmpegStep):
            return self.hasAudio or self.isTrimmed
        return True

    def setName(self, name: str) -> None:
        super().setName(name)
        stem, ext = splitStemExt(self.name)
        cleanStem = TIME_SUFFIX_RE.sub("", stem)
        self.baseName = toSafeFilename(f"{cleanStem}{ext}", fallback=self.name)
        if self.isTrimmed:
            suffix = buildTimeSuffix(self.startTime, self.endTime)
            self.name = toSafeFilename(f"{cleanStem} {suffix}{ext}", fallback=self.baseName)

    def setTimeRange(self, startTime: int, endTime: int) -> None:
        start = max(0, int(startTime))
        end = max(0, int(endTime))
        if self.duration > 0:
            end = min(end, self.duration)
        if (start == 0 and (end == 0 or (self.duration > 0 and end >= self.duration))) or (0 < end <= start):
            self.startTime = 0
            self.endTime = 0
        else:
            self.startTime = start
            self.endTime = end if end > 0 else self.duration

        stem, ext = splitStemExt(self.baseName)
        if self.isTrimmed:
            suffix = buildTimeSuffix(self.startTime, self.endTime)
            self.name = toSafeFilename(f"{stem} {suffix}{ext}", fallback=self.baseName)
        else:
            self.name = self.baseName

        self._syncSteps()
        self._updateFileSize()
        self.updateStatus()

    def _syncSteps(self) -> None:
        effEnd = (self.endTime or self.duration) if self.isTrimmed else 0
        effStart = self.startTime if self.isTrimmed else 0
        for step in self.steps:
            if isinstance(step, FFmpegResourceStep):
                if step.rawFileSize <= 0 and step.fileSize > 0 and not self.isTrimmed:
                    step.rawFileSize = step.fileSize
                step.startTime = effStart
                step.endTime = effEnd
                if step.role == "video" and self.videoIndex is not None:
                    step.headerData = self.videoData
                    step.containerIndex = self.videoIndex
                elif step.role == "audio" and self.audioIndex is not None:
                    step.headerData = self.audioData
                    step.containerIndex = self.audioIndex
                if not self.isTrimmed and step.rawFileSize > 0:
                    step.httpByteOffset = 0
                    step.fileSize = step.rawFileSize
            elif isinstance(step, FFmpegStep):
                step.startTime = effStart
                step.endTime = effEnd

    def _updateFileSize(self) -> None:
        if not self.isTrimmed:
            if self.rawFileSize > 0:
                self.fileSize = self.rawFileSize
            return
        effEnd = self.endTime or self.duration
        total = 0
        for step in self.steps:
            if not isinstance(step, FFmpegResourceStep):
                continue
            stepSize = 0
            if step.headerData and step.containerIndex is not None:
                seg = buildSegmentRange(step.headerData, step.containerIndex, self.startTime, effEnd)
                if seg is not None:
                    stepSize = seg.segEnd - seg.segStart
            if stepSize <= 0 and self.duration > 0 and step.rawFileSize > 0 and effEnd > self.startTime:
                stepSize = max(1, int(step.rawFileSize * (effEnd - self.startTime) / self.duration))
            if stepSize > 0:
                step.fileSize = stepSize
                total += stepSize
        if total > 0:
            self.fileSize = total

    def relink(self, newTask: Task) -> None:
        if newTask.packId not in {"ffmpeg", "http", "github"} or self.hasAudio:
            raise TaskError("该链接不能用于更换")
        old = self.videoStep
        new = newTask.steps[0]
        if not isinstance(new, HttpTaskStep) or not new.canUseRangeRequests:
            raise TaskError("该链接不能用于更换")
        oldRawSize = self.rawFileSize or self.fileSize
        newRawSize = (
            newTask.rawFileSize
            if isinstance(newTask, FFmpegTask) and newTask.rawFileSize > 0
            else new.fileSize
        )
        if oldRawSize <= 0 or newRawSize != oldRawSize:
            raise TaskError("新链接的内容与原任务不同，请重新添加任务")

        old.url = new.url
        old.headers = dict(new.headers)
        old.clientProfile = new.clientProfile
        old.userAgent = new.userAgent
        old.subworkerCount = new.subworkerCount
        old.lastModified = new.lastModified
        if isinstance(newTask, FFmpegTask) and newTask.videoIndex is not None:
            self.videoData = newTask.videoData
            self.videoIndex = newTask.videoIndex
            old.headerData = newTask.videoData
            old.containerIndex = newTask.videoIndex

        if old.status in {TaskStatus.RUNNING, TaskStatus.FAILED}:
            old.status = TaskStatus.PAUSED
            old.error = None
        if self.ffmpegStep.status in {TaskStatus.RUNNING, TaskStatus.FAILED}:
            self.ffmpegStep.status = TaskStatus.PAUSED
            self.ffmpegStep.error = None
        self.url = newTask.url
        self.updateStatus()
