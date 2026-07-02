from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from app.models.task import TaskError, TaskStep, TaskStatus
from app.platform.filesystem import deletePath
from http_pack.task import HttpTaskStep
from .config import ffmpegRuntime


def mediaStem(task) -> str:
    name = task.name
    return name.rsplit(".", 1)[0] if "." in name else name


@dataclass(kw_only=True)
class FFmpegResourceStep(HttpTaskStep):
    role: str = ""
    extension: str = ""

    @property
    def outputPath(self) -> str:
        suffix = f".{self.extension}" if self.extension else ""
        return str(self.task.outputFolder / f"{mediaStem(self.task)}.{self.role}{suffix}")


@dataclass(kw_only=True)
class FFmpegStep(TaskStep):
    canPause = False

    videoExtension: str = ""
    audioExtension: str = ""
    shouldDeleteSource: bool = True

    @property
    def outputFile(self) -> str:
        return str(self.task.outputFolder / f"{mediaStem(self.task)}.mp4")

    @property
    def _videoPath(self) -> Path:
        suffix = f".{self.videoExtension}" if self.videoExtension else ""
        return self.task.outputFolder / f"{mediaStem(self.task)}.video{suffix}"

    @property
    def _audioPath(self) -> Path:
        suffix = f".{self.audioExtension}" if self.audioExtension else ""
        return self.task.outputFolder / f"{mediaStem(self.task)}.audio{suffix}"

    async def run(self) -> None:

        ffmpegPath = ffmpegRuntime.path()
        ffprobePath = ffmpegRuntime.ffprobePath()
        if not ffmpegPath or not ffprobePath:
            raise TaskError("Binary not found: {name}", name="FFmpeg")

        Path(self.outputFile).parent.mkdir(parents=True, exist_ok=True)

        totalDuration = await self._probeDuration(ffprobePath, self._videoPath)

        process = await asyncio.create_subprocess_exec(
            ffmpegPath,
            "-y", "-v", "error", "-nostats", "-progress", "pipe:1",
            "-i", str(self._videoPath),
            "-i", str(self._audioPath),
            "-c", "copy",
            self.outputFile,
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
                    "FFmpeg merge failed ({code}): {detail}",
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
