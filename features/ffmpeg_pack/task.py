import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from app.bases.interfaces import Worker
from app.bases.models import TaskStage, TaskStatus
from .config import ffmpegPaths

if TYPE_CHECKING:
    from features.http_pack.task import HttpTaskStage
else:
    from http_pack.task import HttpTaskStage


def _baseTitle(taskTitle: str) -> str:
    return taskTitle[:-4] if taskTitle.lower().endswith(".mp4") else taskTitle


@dataclass(kw_only=True)
class FFmpegResourceStage(HttpTaskStage):
    # role ∈ {"video", "audio"}：合并任务里两路源各自的角色，落盘文件名带这个中缀
    role: str = "video"
    extension: str = ""

    def updateOutputFile(self, taskPath: Path, taskTitle: str):
        suffix = f".{self.extension}" if self.extension else ""
        self.outputFile = str(taskPath / f"{_baseTitle(taskTitle)}.{self.role}{suffix}")


def _parseDuration(value: str) -> float:
    try:
        return max(0.0, float(value))
    except ValueError:
        return 0.0


async def _probeDuration(ffprobe: str, path: Path) -> float:
    process = await asyncio.create_subprocess_exec(
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        message = stderr.decode("utf-8", errors="ignore").strip()
        logger.warning("ffprobe 获取时长失败: {}, {}", path, message or process.returncode)
        return 0.0

    return _parseDuration(stdout.decode("utf-8", errors="ignore").strip())


@dataclass(kw_only=True)
class FFmpegStage(TaskStage):
    workerType: type = field(init=False, repr=False)
    canPause: bool = field(init=False, default=False)

    videoPath: Path = field(default_factory=Path)
    audioPath: Path = field(default_factory=Path)
    outputFile: Path = field(default_factory=Path)
    videoExtension: str = ""
    audioExtension: str = ""
    cleanupSource: bool = True

    def updateOutputFile(self, taskPath: Path, taskTitle: str):
        baseTitle = _baseTitle(taskTitle)
        videoSuffix = f".{self.videoExtension}" if self.videoExtension else ""
        audioSuffix = f".{self.audioExtension}" if self.audioExtension else ""
        self.outputFile = taskPath / f"{baseTitle}.mp4"
        self.videoPath = taskPath / f"{baseTitle}.video{videoSuffix}"
        self.audioPath = taskPath / f"{baseTitle}.audio{audioSuffix}"


class FFmpegWorker(Worker):
    def __init__(self, stage: FFmpegStage):
        super().__init__(stage)
        self.stage = stage

    async def _readProgress(self, stream: asyncio.StreamReader, totalDuration: float):
        while True:
            rawLine = await stream.readline()
            if not rawLine:
                break

            line = rawLine.decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            if line.startswith("out_time_us=") and totalDuration > 0:
                currentDuration = _parseDuration(line.removeprefix("out_time_us=")) / 1_000_000
                if currentDuration <= 0:
                    continue
                self.stage.progress = min(99.5, max(0.0, currentDuration / totalDuration * 100))
            elif line == "progress=end":
                self.stage.progress = 100

    async def run(self):
        ffmpeg, ffprobe = ffmpegPaths()
        if not ffmpeg or not ffprobe:
            raise RuntimeError("未找到可用的 ffmpeg 和 ffprobe，请先在设置中安装或配置 FFmpeg")

        self.stage.outputFile.parent.mkdir(parents=True, exist_ok=True)

        process = None
        progressTask = None
        try:
            totalDuration = await _probeDuration(ffprobe, self.stage.videoPath)
            process = await asyncio.create_subprocess_exec(
                ffmpeg,
                "-y", "-v", "error", "-nostats", "-progress", "pipe:1",
                "-i", self.stage.videoPath,
                "-i", self.stage.audioPath,
                "-c", "copy",
                self.stage.outputFile,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            progressTask = asyncio.create_task(self._readProgress(process.stdout, totalDuration))

            await process.wait()
            await progressTask
            if process.returncode != 0:
                stderrOutput = (await process.stderr.read()).decode("utf-8", errors="ignore").strip()
                suffix = f", {stderrOutput}" if stderrOutput else ""
                raise RuntimeError(f"ffmpeg 退出码异常: {process.returncode}{suffix}")

            self.stage.setStatus(TaskStatus.COMPLETED)
            if self.stage.cleanupSource:
                # 同时清理 HttpWorker 写下的 .ghd 临时元数据文件
                for path in (self.stage.videoPath, self.stage.audioPath):
                    for target in (path, path.with_name(f"{path.name}.ghd")):
                        try:
                            target.unlink(missing_ok=True)
                        except OSError as e:
                            logger.opt(exception=e).warning("failed to cleanup temporary file {}", target)
        except asyncio.CancelledError:
            self.stage.setStatus(TaskStatus.PAUSED)
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()
            if progressTask is not None and not progressTask.done():
                progressTask.cancel()
                with suppress(asyncio.CancelledError):
                    await progressTask
            raise
        except Exception as e:
            self.stage.setError(e)
            raise


FFmpegStage.workerType = FFmpegWorker
