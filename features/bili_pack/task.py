import asyncio
import time
import shutil
from asyncio import CancelledError
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
    durationUs: int = field(default=0)
    cleanupSource: bool = field(default=True)


class FFmpegWorker(Worker):
    def __init__(self, stage: FFmpegStage):
        super().__init__(stage)
        self.stage = stage

    async def run(self):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.stage.setStatus(TaskStatus.FAILED)
            raise RuntimeError("未找到 ffmpeg，请先将 ffmpeg 加入 PATH")

        outputPath = Path(self.stage.resolvePath)
        outputPath.parent.mkdir(parents=True, exist_ok=True)

        process = None
        stderrTask = None
        try:
            self.stage.progress = 0
            self.stage.speed = 0
            self.stage.receivedBytes = 0
            process = await asyncio.create_subprocess_exec(
                ffmpeg,
                "-y",
                "-nostats",
                "-loglevel",
                "error",
                "-i",
                self.stage.videoPath,
                "-i",
                self.stage.audioPath,
                "-c",
                "copy",
                "-progress",
                "pipe:1",
                self.stage.resolvePath,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stderrTask = asyncio.create_task(process.stderr.read())
            await self._watchProgress(process)
            stderr = await stderrTask
            await process.wait()
            if process.returncode != 0:
                message = stderr.decode("utf-8", errors="ignore").strip()
                raise RuntimeError(message or f"ffmpeg 退出码异常: {process.returncode}")

            self.stage.setStatus(TaskStatus.COMPLETED)
            if self.stage.cleanupSource:
                self._cleanupSourceFiles()
        except CancelledError:
            self.stage.setStatus(TaskStatus.PAUSED)
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()
            if stderrTask is not None and not stderrTask.done():
                stderrTask.cancel()
            raise
        except Exception:
            self.stage.setStatus(TaskStatus.FAILED)
            if stderrTask is not None and not stderrTask.done():
                stderrTask.cancel()
            raise

    async def _watchProgress(self, process: asyncio.subprocess.Process):
        if process.stdout is None:
            return

        durationUs = self.stage.durationUs
        lastOutputSize = 0
        lastSpeedCheck = time.monotonic()
        progressData: dict[str, str] = {}

        while True:
            line = await process.stdout.readline()
            if not line:
                break

            text = line.decode("utf-8", errors="ignore").strip()
            if not text or "=" not in text:
                continue

            key, value = text.split("=", 1)
            progressData[key] = value

            if key != "progress":
                continue

            currentOutputSize = self._safeParseInt(progressData.get("total_size"))
            currentUs = self._parseOutputTimeUs(progressData)

            now = time.monotonic()
            elapsed = max(now - lastSpeedCheck, 1e-3)
            self.stage.speed = max(int((currentOutputSize - lastOutputSize) / elapsed), 0)
            lastOutputSize = currentOutputSize
            lastSpeedCheck = now

            if durationUs > 0 and currentUs >= 0:
                self.stage.progress = min((currentUs / durationUs) * 100, 99.9)

            if value == "end":
                break

            progressData.clear()

    def _parseOutputTimeUs(self, progressData: dict[str, str]) -> int:
        if "out_time_us" in progressData:
            return self._safeParseInt(progressData.get("out_time_us"))

        outTime = progressData.get("out_time")
        if outTime:
            try:
                hour, minute, second = outTime.split(":")
                totalSeconds = int(hour) * 3600 + int(minute) * 60 + float(second)
            except (TypeError, ValueError):
                totalSeconds = None
            if totalSeconds is not None:
                return int(totalSeconds * 1_000_000)

        return self._safeParseInt(progressData.get("out_time_ms"))

    def _safeParseInt(self, value: str | None) -> int:
        if value is None:
            return 0

        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

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
        except CancelledError:
            logger.info(f"{self.title} 停止下载")
            raise
        except Exception as e:
            logger.error(f"{self.title} 下载失败: {repr(e)}")
            raise

    def __hash__(self):
        return hash(self.taskId)
