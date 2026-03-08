import asyncio
import shutil
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

from loguru import logger

from app.bases.interfaces import Worker
from app.bases.models import Task, TaskStage, TaskStatus
from app.supports.config import DEFAULT_HEADERS
from app.supports.utils import getProxies

if TYPE_CHECKING:
    from features.http_pack.task import HttpTaskStage, HttpWorker
else:
    from http_pack.task import HttpTaskStage, HttpWorker


@dataclass
class FFmpegStage(TaskStage):
    videoPath: str
    audioPath: str
    resolvePath: str
    cleanupSource: bool = field(default=True)


class FFmpegWorker(Worker):
    def __init__(self, stage: FFmpegStage):
        super().__init__(stage)
        self.stage = stage

    @staticmethod
    def _parseDuration(value: Any) -> float:
        try:
            duration = float(value)
        except (TypeError, ValueError):
            return 0.0

        if duration > 0:
            return duration
        return 0.0

    async def _probeDuration(self, ffprobe: str, path: str) -> float:
        process = await asyncio.create_subprocess_exec(
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="ignore").strip()
            logger.warning(f"ffprobe 获取时长失败: {path}, {message or process.returncode}")
            return 0.0

        return self._parseDuration(stdout.decode("utf-8", errors="ignore").strip())

    async def _probeVideoDuration(self, ffprobe: str | None) -> float:
        if not ffprobe:
            logger.warning("未找到 ffprobe，视频合并进度将在完成时更新")
            return 0.0

        return await self._probeDuration(ffprobe, self.stage.videoPath)

    async def _readProgress(self, stream: asyncio.StreamReader | None, totalDuration: float):
        if stream is None:
            return

        while True:
            rawLine = await stream.readline()
            if not rawLine:
                break

            line = rawLine.decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            if line.startswith("out_time_us=") and totalDuration > 0:
                currentDuration = self._parseDuration(line.removeprefix("out_time_us=")) / 1_000_000
                if currentDuration <= 0:
                    continue
                self.stage.progress = min(99.5, max(0.0, currentDuration / totalDuration * 100))
            elif line == "progress=end":
                self.stage.progress = 100

    async def run(self):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.stage.setStatus(TaskStatus.FAILED)
            raise RuntimeError("未找到 ffmpeg，请先将 ffmpeg 加入 PATH")
        ffprobe = shutil.which("ffprobe")

        outputPath = Path(self.stage.resolvePath)
        outputPath.parent.mkdir(parents=True, exist_ok=True)

        process = None
        progressTask = None
        try:
            self.stage.progress = 0
            self.stage.speed = 0
            self.stage.receivedBytes = 0
            totalDuration = await self._probeVideoDuration(ffprobe)
            process = await asyncio.create_subprocess_exec(
                ffmpeg,
                "-y",
                "-v",
                "error",
                "-nostats",
                "-progress",
                "pipe:1",
                "-i",
                self.stage.videoPath,
                "-i",
                self.stage.audioPath,
                "-c",
                "copy",
                self.stage.resolvePath,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            progressTask = asyncio.create_task(self._readProgress(process.stdout, totalDuration))

            await process.wait()
            await progressTask
            if process.returncode != 0:
                raise RuntimeError(f"ffmpeg 退出码异常: {process.returncode}")

            self.stage.setStatus(TaskStatus.COMPLETED)
            if self.stage.cleanupSource:
                self._cleanupSourceFiles()
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
        except Exception:
            self.stage.setStatus(TaskStatus.FAILED)
            raise

    def _cleanupSourceFiles(self):
        for rawPath in (self.stage.videoPath, self.stage.audioPath):
            target = Path(rawPath)
            for path in (target, Path(str(target) + ".ghd")):
                try:
                    if path.is_file() or path.is_symlink():
                        path.unlink()
                except FileNotFoundError:
                    continue
                except Exception as e:
                    logger.error(f"failed to cleanup temporary file {path}: {repr(e)}")


@dataclass
class BilibiliTask(Task):
    url: str
    headers: dict = field(default_factory=DEFAULT_HEADERS.copy)
    proxies: dict = field(default_factory=getProxies)
    blockNum: int = field(default=8)
    pageNumber: int = field(default=1)
    videoStageId: str = field(default="")
    audioStageId: str = field(default="")
    mergeStageId: str = field(default="")
    videoPath: str = field(default="")
    audioPath: str = field(default="")

    def __post_init__(self):
        super().__post_init__()
        self._ensureStageIds()
        self.syncStagePaths()

    def _ensureStageIds(self):
        httpStages = [stage for stage in self.stages if isinstance(stage, HttpTaskStage)]
        mergeStages = [stage for stage in self.stages if isinstance(stage, FFmpegStage)]

        if not self.videoStageId and len(httpStages) >= 1:
            self.videoStageId = httpStages[0].stageId
        if not self.audioStageId and len(httpStages) >= 2:
            self.audioStageId = httpStages[1].stageId
        if not self.mergeStageId and mergeStages:
            self.mergeStageId = mergeStages[-1].stageId

    def _buildStagePaths(self) -> tuple[str, str]:
        finalPath = Path(self.resolvePath)
        videoPath = finalPath.with_name(f"{finalPath.stem}.video.m4s")
        audioPath = finalPath.with_name(f"{finalPath.stem}.audio.m4s")
        return str(videoPath), str(audioPath)

    def setTitle(self, title: str):
        self.title = title

    def syncStagePaths(self):
        self.videoPath, self.audioPath = self._buildStagePaths()
        for stage in self.stages:
            if isinstance(stage, HttpTaskStage):
                if stage.stageId == self.videoStageId:
                    stage.resolvePath = self.videoPath
                elif stage.stageId == self.audioStageId:
                    stage.resolvePath = self.audioPath
            elif isinstance(stage, FFmpegStage):
                stage.videoPath = self.videoPath
                stage.audioPath = self.audioPath
                stage.resolvePath = self.resolvePath

    def applyPayloadToTask(self, payload: dict[str, Any]):
        super().applyPayloadToTask(payload)

        proxies = payload.get("proxies")
        if isinstance(proxies, dict):
            self.proxies = proxies

        blockNum = payload.get("preBlockNum")
        if isinstance(blockNum, int):
            self.blockNum = blockNum

        self.syncStagePaths()
        for stage in self.stages:
            if isinstance(stage, HttpTaskStage):
                if isinstance(proxies, dict):
                    stage.proxies = proxies
                if isinstance(blockNum, int):
                    stage.blockNum = blockNum

    async def run(self):
        self.stages.sort(key=lambda stage: stage.stageIndex)
        try:
            for stage in self.stages:
                if self.status != TaskStatus.RUNNING:
                    break
                if stage.status == TaskStatus.COMPLETED:
                    continue

                if isinstance(stage, HttpTaskStage):
                    await HttpWorker(stage).run()
                    continue

                if isinstance(stage, FFmpegStage):
                    await FFmpegWorker(stage).run()
                    continue

                raise TypeError(f"不支持的 BilibiliTaskStage: {type(stage).__name__}")
        except asyncio.CancelledError:
            logger.info(f"{self.title} 停止下载")
            raise
        except Exception as e:
            logger.error(f"{self.title} 下载失败: {repr(e)}")
            raise

    def __hash__(self):
        return hash(self.taskId)
