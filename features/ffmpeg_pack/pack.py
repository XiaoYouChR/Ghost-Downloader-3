from app.bases.interfaces import FeaturePack
from app.bases.models import Task
from app.view.components.cards import UniversalTaskCard

from .config import ffmpegConfig
from .task import FFmpegInstallTask


class FFmpegPack(FeaturePack):
    taskType = FFmpegInstallTask
    config = ffmpegConfig

    def createTaskCard(self, task: Task, parent=None):
        if isinstance(task, FFmpegInstallTask):
            return UniversalTaskCard(task, parent)
        return None
