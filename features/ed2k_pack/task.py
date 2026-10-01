from __future__ import annotations

from dataclasses import dataclass

from app.models.task import Task, TaskError, TaskStep, TaskStatus
from .python_ed2k import Transfer


@dataclass(kw_only=True, eq=False)
class ED2kTask(Task):
    packId: str = "ed2k"
    canSeed = True
    fileHash: str = ""
    activePeerCount: int | None = None
    totalPeerCount: int = 0
    uploadRate: int = 0
    uploadedBytes: int = 0
    seedingTimeSeconds: int = 0

    @property
    def shareRatioPercent(self) -> float:
        return self.uploadedBytes / self.fileSize * 100 if self.fileSize > 0 else 0.0

    def reset(self) -> TaskStatus:
        self.fileHash = ""
        self.activePeerCount = None
        self.totalPeerCount = 0
        self.uploadRate = 0
        self.uploadedBytes = 0
        self.seedingTimeSeconds = 0
        return super().reset()

    async def runSeeding(self, isManual: bool) -> None:
        from .session import ed2kSession

        def onProgress(t: Transfer, elapsed: int, uploaded: int):
            self.uploadRate = t.uploadRate
            self.uploadedBytes = uploaded
            self.activePeerCount = t.activePeers
            self.totalPeerCount = t.peers
            self.seedingTimeSeconds = elapsed

        try:
            await ed2kSession.runSeeding(
                self.url, self.fileHash, self.seedingTimeSeconds, self.uploadedBytes,
                isManual, onProgress)
        finally:
            self.uploadRate = 0

    def deleteFiles(self):
        if self.fileHash:
            from .session import ed2kSession
            ed2kSession.remove(self.fileHash)
        super().deleteFiles()


@dataclass(kw_only=True)
class ED2kTaskStep(TaskStep):
    async def run(self, reportSpeed, waitForSpeedLimit) -> None:
        from .session import RunResult, ed2kSession

        task: ED2kTask = self.task

        def onStarted(result: RunResult):
            if result.name != task.name:
                raise TaskError("该文件已由另一个任务在下载")
            task.fileHash = result.fileHash
            if result.fileSize:
                task.fileSize = result.fileSize

        def onProgress(t: Transfer, uploaded: int):
            task.uploadRate = t.uploadRate
            task.uploadedBytes = uploaded
            task.activePeerCount = t.activePeers
            task.totalPeerCount = t.peers
            self.receivedBytes = t.received
            self.speed = t.downloadRate
            reportSpeed(t.downloadRate)
            if t.size > 0:
                task.fileSize = t.size
                self.progress = min(99.9, t.received / t.size * 100)

        await ed2kSession.run(
            task.url, task.fileHash, task.name, task.outputFolder, task.uploadedBytes,
            onStarted=onStarted,
            onProgress=onProgress,
        )
