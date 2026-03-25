from app.bases.interfaces import FeaturePack
from app.bases.models import Task
from app.view.components.cards import UniversalTaskCard, UniversalResultCard

from .config import ffmpegConfig
from .task import FFmpegInstallTask, FFmpegMergeTask, createBrowserMergeTask


FFMPEG_MERGE_URL = "gd3+ffmpeg://merge"


class FFmpegPack(FeaturePack):
    taskType = (FFmpegInstallTask, FFmpegMergeTask)
    config = ffmpegConfig

    def canHandle(self, url: str) -> bool:
        return str(url).strip() == FFMPEG_MERGE_URL

    async def parse(self, payload: dict) -> Task:
        return await createBrowserMergeTask(payload)

    def createTaskCard(self, task: Task, parent=None):
        if isinstance(task, (FFmpegInstallTask, FFmpegMergeTask)):
            return UniversalTaskCard(task, parent)
        return None

    def createResultCard(self, task: Task, parent=None):
        if isinstance(task, (FFmpegInstallTask, FFmpegMergeTask)):
            return UniversalResultCard(task, parent)
        return None
