from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.models.task import Task, TaskStep, TaskStatus
from .config import ed2kConfig
from .session import ed2kSession


@dataclass(kw_only=True, eq=False)
class ED2kTask(Task):
    packId: str = "ed2k"
    canSeed = True
    uploadedBytes: int = 0
    seedingTimeSeconds: int = 0

    @property
    def shareRatioPercent(self) -> float:
        return self.uploadedBytes / self.fileSize * 100 if self.fileSize > 0 else 0.0

    def reset(self) -> TaskStatus:
        ed2kSession.delete(self)
        self.uploadedBytes = 0
        self.seedingTimeSeconds = 0
        return super().reset()

    async def runSeeding(self, isManual: bool) -> None:
        loop = asyncio.get_running_loop()
        seedingStart = loop.time() - self.seedingTimeSeconds
        async with ed2kSession.run(self, isSeed=True) as progresses:
            async for progress in progresses:
                self.uploadedBytes = progress.uploaded
                self.seedingTimeSeconds = int(loop.time() - seedingStart)
                if not isManual and isSeedingLimitReached(self.seedingTimeSeconds, progress.uploaded, progress.size):
                    return

    def deletePlaceholders(self) -> None:
        ed2kSession.delete(self)
        super().deletePlaceholders()


@dataclass(kw_only=True)
class ED2kTaskStep(TaskStep):
    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        task: ED2kTask = self.task
        async with ed2kSession.run(task, isSeed=False) as progresses:
            async for progress in progresses:
                task.uploadedBytes = progress.uploaded
                reportSpeed(max(0, progress.received - self.receivedBytes))
                self.receivedBytes = progress.received
                self.speed = progress.downloadRate
                self.progress = min(99.9, progress.received / progress.size * 100)


def isSeedingLimitReached(elapsed: int, uploaded: int, size: int) -> bool:
    ratioLimit = ed2kConfig.seedingRatioLimit.value
    if ratioLimit > 0 and size > 0 and uploaded * 100 >= ratioLimit * size:
        return True
    timeLimit = ed2kConfig.seedingTimeLimit.value
    return timeLimit > 0 and elapsed >= timeLimit * 60
