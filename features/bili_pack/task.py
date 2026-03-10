import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

from loguru import logger

from app.bases.models import Task, TaskStatus
from app.supports.config import DEFAULT_HEADERS
from app.supports.utils import getProxies

if TYPE_CHECKING:
    from features.ffmpeg_pack.task import FFmpegStage, FFmpegWorker
    from features.http_pack.task import HttpTaskStage, HttpWorker
else:
    from ffmpeg_pack.task import FFmpegStage, FFmpegWorker
    from http_pack.task import HttpTaskStage, HttpWorker


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
            logger.opt(exception=e).error("{} 下载失败", self.title)
            raise

    def __hash__(self):
        return hash(self.taskId)
