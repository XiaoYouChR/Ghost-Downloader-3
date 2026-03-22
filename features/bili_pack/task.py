import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

from loguru import logger

from app.bases.models import Task, TaskStatus
from app.supports.config import DEFAULT_HEADERS, cfg
from app.supports.utils import getProxies

if TYPE_CHECKING:
    from features.ffmpeg_pack.task import FFmpegStage, FFmpegWorker
    from features.http_pack.task import HttpTaskStage, HttpWorker
else:
    from ffmpeg_pack.task import FFmpegStage, FFmpegWorker
    from http_pack.task import HttpTaskStage, HttpWorker


@dataclass
class BilibiliTask(Task):
    headers: dict = field(default_factory=DEFAULT_HEADERS.copy)
    proxies: dict = field(default_factory=getProxies)
    blockNum: int = field(default_factory=lambda: cfg.preBlockNum.value)
    selectedPages: list[int] = field(default_factory=list)
    pageParts: list[str] = field(default_factory=list)
    totalPages: int = field(default=1)

    def __post_init__(self):
        super().__post_init__()
        self.syncStagePaths()

    @property
    def resolvePath(self) -> str:
        if not self.selectedPages:
            return str(self.path / self.title)

        return str(self.path / self._buildOutputFileName(0))

    def _baseTitle(self) -> str:
        return self.title[:-4] if self.title.lower().endswith(".mp4") else self.title

    def _buildOutputFileName(self, index: int) -> str:
        baseTitle = self._baseTitle()
        if len(self.selectedPages) <= 1:
            return f"{baseTitle}.mp4"

        pageNumber = self.selectedPages[index]
        pagePart = self.pageParts[index] if index < len(self.pageParts) else ""
        suffix = f"P{pageNumber}"
        if pagePart and pagePart != baseTitle:
            return f"{baseTitle} - {suffix} {pagePart}.mp4"
        return f"{baseTitle} - {suffix}.mp4"

    def syncStagePaths(self):
        for index in range(len(self.selectedPages)):
            stages = self.stages[index * 3:(index + 1) * 3]
            if len(stages) != 3:
                continue

            videoStage, audioStage, mergeStage = stages
            finalPath = Path(self.path / self._buildOutputFileName(index))
            videoPath = finalPath.with_name(f"{finalPath.stem}.video.m4s")
            audioPath = finalPath.with_name(f"{finalPath.stem}.audio.m4s")

            videoStage.resolvePath = str(videoPath)
            audioStage.resolvePath = str(audioPath)
            mergeStage.videoPath = str(videoPath)
            mergeStage.audioPath = str(audioPath)
            mergeStage.resolvePath = str(finalPath)

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
        currentStage = None
        try:
            for stage in self.iterRunnableStages():
                currentStage = stage
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
            if currentStage is not None and not currentStage.error:
                currentStage.setError(e)
            logger.opt(exception=e).error("{} 下载失败", self.title)
            raise

    def __hash__(self):
        return hash(self.taskId)
