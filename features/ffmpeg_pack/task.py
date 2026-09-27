from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from app.models.task import Task, TaskError, TaskStep, TaskStatus
from app.platform.filesystem import deletePath
from http_pack.task import HttpTaskStep
from .config import ffmpegRuntime


ISOBMFF_BOX_TYPES = {b'ftyp', b'styp', b'moof', b'moov', b'free', b'skip', b'mdat', b'pdin'}


def toResourcePath(task: Task, role: str, extension: str) -> Path:
    return task.partPath / (f"{role}.{extension}" if extension else role)


@dataclass(kw_only=True)
class FFmpegResourceStep(HttpTaskStep):
    role: str = ""
    extension: str = ""

    @property
    def outputPath(self) -> str:
        return str(toResourcePath(self.task, self.role, self.extension))


@dataclass(kw_only=True)
class FFmpegStep(TaskStep):
    canPause = False

    videoExtension: str = ""
    audioExtension: str = ""
    shouldDeleteSource: bool = True

    @property
    def outputPath(self) -> str:
        return self.task.outputPath

    @property
    def _videoPath(self) -> Path:
        return toResourcePath(self.task, "video", self.videoExtension)

    @property
    def _audioPath(self) -> Path:
        return toResourcePath(self.task, "audio", self.audioExtension)

    async def run(self, reportSpeed, waitForSpeedLimit) -> None:

        ffmpegPath = ffmpegRuntime.path()
        ffprobePath = ffmpegRuntime.ffprobePath()
        if not ffmpegPath or not ffprobePath:
            raise TaskError("{name} 未安装，请在设置中安装", name="FFmpeg")

        totalDuration = await self._probeDuration(ffprobePath, self._videoPath)

        process = await asyncio.create_subprocess_exec(
            ffmpegPath,
            "-y", "-v", "error", "-nostats", "-progress", "pipe:1",
            "-i", str(self._videoPath),
            "-i", str(self._audioPath),
            "-c", "copy",
            self.outputPath,
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
                for inputPath in (self._videoPath, self._audioPath):
                    if inputPath.exists():
                        with open(inputPath, "rb") as f:
                            boxType = f.read(8)[4:8]
                        if boxType not in ISOBMFF_BOX_TYPES:
                            raise TaskError(
                                "文件不是有效的媒体格式，可能受 DRM 保护或下载不完整：{name}",
                                name=inputPath.name,
                            )
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

    async def _readProgress(self, stream: asyncio.StreamReader, totalDuration: float):
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
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            logger.warning("ffprobe 获取时长失败: {}", videoPath)
            return 0.0
        try:
            return max(0.0, float(stdout.decode("utf-8", errors="ignore").strip()))
        except ValueError:
            return 0.0
